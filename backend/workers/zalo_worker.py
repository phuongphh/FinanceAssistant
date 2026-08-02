"""Background worker for inbound Zalo OA events (Phase 5.0 #2.2).

Same shape as :mod:`backend.workers.telegram_worker`, one channel over:
the webhook claims a ``zalo_updates`` row and spawns
:func:`process_event_safely` via ``asyncio.create_task``, so the HTTP
response is never blocked on an LLM call.

This module owns:

- :func:`route_event` — open a session, record the 48h reply window,
  dispatch one event to the Zalo inbound handler, commit at the
  boundary. (Two commits, not one: see :func:`_open_reply_window` for
  why the window has to land before the handler runs.)
- :func:`process_event_safely` — never-raise wrapper that marks the
  ``zalo_updates`` row ``done``/``failed``.
- :func:`recover_orphaned_events` — re-enqueue rows stuck in
  ``processing`` after a crash.

Why this is a separate module rather than a generic queue shared with
Telegram: the two queues have different primary key types (``String``
vs ``BigInteger``), different retry semantics on the provider side, and
Zalo's 48h reply window means a recovered event may no longer be
answerable at all. Folding them together would mean parameterising the
Telegram hot path for a channel that is still behind a flag. Worth
revisiting once Zalo reaches parity (Phase 5.1).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.channel_context import CHANNEL_ZALO, use_channel
from backend.config import get_settings
from backend.database import get_session_factory
from backend.models.zalo_update import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    ZaloUpdate,
)
from backend.services import zalo_window_service
from backend.utils.zalo_events import parse_event

logger = logging.getLogger(__name__)

# How long a row may sit in ``processing`` before we treat it as
# orphaned. Matches the Telegram worker: long enough that a genuinely
# slow LLM call is not re-run, short enough that a crashed worker's
# work is picked up quickly.
ORPHAN_CUTOFF = timedelta(minutes=5)

# Cap per recovery pass so a long outage doesn't spawn thousands of
# tasks at once. Anything above the cap waits for the next pass.
ORPHAN_BATCH_LIMIT = 100

# Must be shorter than ORPHAN_CUTOFF so a freshly stuck row is picked up
# within one cutoff window no matter when it went stale.
RECOVERY_INTERVAL = 120  # seconds


async def route_event(payload: dict) -> UUID | None:
    """Dispatch one Zalo event to the inbound handler.

    Opens a fresh ``AsyncSession`` — by the time this background task
    runs, the webhook's session is closed. Commits on success; on
    exception the session context manager rolls back and the caller
    marks the row ``failed``.

    Returns the resolved ``users.id`` when the sender is linked, so the
    caller can stamp it on the ``zalo_updates`` row. ``None`` for
    unlinked senders — they have no user row yet, which is exactly why
    ``zalo_updates.user_id`` is nullable.

    Re-parses ``payload`` rather than taking a :class:`ZaloEvent`
    argument: orphan recovery only has the stored JSON to work from, so
    parsing here keeps the recovered path and the live path identical.
    """
    # Local import — the handler pulls in the intent stack, and paying
    # that import cost at module load would slow every process that
    # merely touches the models.
    from backend.bot.handlers import zalo_inbound

    settings = get_settings()
    event = parse_event(payload, app_id=settings.zalo_app_id)
    if event is None:
        # The router already validated this payload before claiming the
        # row, so reaching here means the body changed shape between
        # claim and dispatch (only possible via a hand-edited row).
        logger.warning("zalo.worker unusable payload — dropping")
        return None

    session_factory = get_session_factory()
    # Everything downstream of here answers on Zalo. Set once, at the
    # task boundary, so shared intent handlers that send their own reply
    # (#2.4) pick the right renderer without a channel argument threaded
    # through the dispatcher. Both the live path and orphan recovery
    # funnel through this function, so neither can miss it.
    with use_channel(CHANNEL_ZALO):
        async with session_factory() as db:
            await _open_reply_window(db, event)

            user_id = await zalo_inbound.handle_inbound_event(db, event=event)
            if user_id is not None:
                # Records the binding discovered while handling the event
                # (a /link token consumed, an existing account resolved).
                # Only fills an empty slot, so it can never re-point a
                # window at a different account.
                await zalo_window_service.bind_user(
                    db, zalo_user_id=event.sender_id, user_id=user_id
                )
            await db.commit()
            return user_id


async def _open_reply_window(db: AsyncSession, event) -> None:
    """Record the inbound message and **commit** before handling it.

    Two commits in one worker pass looks like a contract violation, so
    here is why it isn't optional.

    The reply window has to be durable before the handler runs.
    ``reserve_send`` deliberately runs in its *own* committed
    transaction — that separate transaction is the whole basis of the
    quota guarantee (see
    :mod:`backend.services.zalo_window_service`) — which means it
    cannot see anything this session has merely flushed. Leave the
    window on the final commit and every reply to a first message would
    be refused with ``no_window``: the user says "ăn trưa 50k", we
    record it, and answer nothing.

    So the ordering is: open the window, commit, then handle. The cost
    of the extra round trip is one small upsert on a path that is about
    to make an LLM call, and the failure mode it trades into is benign —
    a crash between the two commits leaves a window row for a message we
    never processed, which expires on its own in 48h.

    Non-text events (follow, delivery receipts) don't open a reply
    window here; the router already drops them before claiming a row,
    and the check keeps the recovery path honest if that ever changes.
    """
    if not event.is_text:
        return
    await zalo_window_service.record_inbound(db, zalo_user_id=event.sender_id)
    await db.commit()


async def process_event_safely(msg_id: str, payload: dict) -> None:
    """Background-task wrapper — never raises.

    A handler bug must not kill the event loop, and it must never
    surface to Zalo as a non-2xx (the webhook has already answered 200
    by this point anyway). Failures are recorded on the row so an
    operator can replay from ``zalo_updates``.
    """
    try:
        user_id = await route_event(payload)
        await _mark_status(msg_id, STATUS_DONE, user_id=user_id)
    except Exception as exc:  # noqa: BLE001 — swallowing is the point.
        logger.exception("zalo.worker route_event failed: msg_id=%s", msg_id)
        await _mark_status(msg_id, STATUS_FAILED, error=str(exc)[:2000])


async def _mark_status(
    msg_id: str,
    status: str,
    *,
    error: str | None = None,
    user_id: UUID | None = None,
) -> None:
    """Record the terminal state of one event.

    ``user_id`` is only written when we resolved one — a failed event
    must not clear a binding an earlier successful pass recorded.
    """
    values: dict = {
        "status": status,
        "processed_at": datetime.utcnow(),
        "error_message": error,
    }
    if user_id is not None:
        values["user_id"] = user_id

    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            await db.execute(
                sa_update(ZaloUpdate)
                .where(ZaloUpdate.msg_id == msg_id)
                .values(**values)
            )
            await db.commit()
        except Exception:
            # Best-effort: never mask the real error the caller is
            # trying to report.
            logger.exception(
                "zalo.worker failed to mark msg_id=%s as %s", msg_id, status
            )
            await db.rollback()


async def _claim_orphan(db: AsyncSession, msg_id: str, cutoff: datetime) -> bool:
    """Atomically claim one stale ``processing`` row.

    Bumps ``received_at`` only while the row is still ``processing``
    AND older than ``cutoff``. The row lock taken by the UPDATE
    serialises concurrent uvicorn workers: the first one's predicate
    matches (rowcount 1), the rest find ``received_at`` already past
    the cutoff and match nothing.
    """
    result = await db.execute(
        sa_update(ZaloUpdate)
        .where(
            ZaloUpdate.msg_id == msg_id,
            ZaloUpdate.status == STATUS_PROCESSING,
            ZaloUpdate.received_at < cutoff,
        )
        .values(received_at=datetime.utcnow())
    )
    await db.commit()
    return result.rowcount == 1


async def recover_orphaned_events() -> int:
    """Re-enqueue Zalo events stuck in ``processing`` from a prior run.

    Runs at startup and on a timer. Each candidate is claimed before it
    is scheduled, so exactly one worker dispatches each orphan even with
    several uvicorn workers running. Returns the number of tasks spawned.

    Note the channel-specific caveat: Zalo's 48h reply window means a
    recovered event may no longer be answerable. Recovery still runs —
    capturing the transaction is worth doing even when the confirmation
    can't be delivered — and the window service is what declines the
    send, not this loop.
    """
    cutoff = datetime.utcnow() - ORPHAN_CUTOFF
    session_factory = get_session_factory()

    spawned = 0
    candidates: list = []
    async with session_factory() as db:
        candidates = (
            await db.execute(
                select(ZaloUpdate.msg_id, ZaloUpdate.payload)
                .where(
                    ZaloUpdate.status == STATUS_PROCESSING,
                    ZaloUpdate.received_at < cutoff,
                )
                .order_by(ZaloUpdate.received_at.asc())
                .limit(ORPHAN_BATCH_LIMIT)
            )
        ).all()

        for msg_id, payload in candidates:
            if await _claim_orphan(db, msg_id, cutoff):
                asyncio.create_task(process_event_safely(msg_id, payload))
                spawned += 1

    if spawned:
        logger.info(
            "zalo.worker recovered %d orphaned event(s) (%d candidates inspected)",
            spawned,
            len(candidates),
        )
    return spawned


async def run_recovery_loop(interval_seconds: int = RECOVERY_INTERVAL) -> None:
    """Periodically re-enqueue orphans. Started from the FastAPI lifespan.

    Exits cleanly on ``CancelledError`` (shutdown). Any other exception
    is logged and the loop continues — recovery is advisory, and one bad
    pass must not silently disable it for the rest of the process's life.
    """
    logger.info(
        "zalo.worker orphan recovery loop started (interval=%ss)", interval_seconds
    )
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await recover_orphaned_events()
            except Exception:
                logger.exception("zalo.worker recovery pass failed; continuing loop")
    except asyncio.CancelledError:
        logger.info("zalo.worker orphan recovery loop cancelled")
        raise
