"""Background worker for Telegram updates.

The webhook route claims an ``update_id`` row and spawns
``process_update_safely`` via ``asyncio.create_task``. This module owns:

- ``route_update`` — dispatch a raw Telegram update dict to the right
  handler (message / callback / onboarding). Opens its own DB session
  because the webhook's session has already been closed by the time the
  background task runs.
- ``process_update_safely`` — never-raise wrapper that marks the
  ``telegram_updates`` row as done/failed.
- ``recover_orphaned_updates`` — scan for rows stuck in ``processing``
  at startup and re-enqueue them.

See docs/archive/scaling-refactor-A.md §A3 + §A1 for context.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session_factory
from backend.models.telegram_update import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    TelegramUpdate,
)

logger = logging.getLogger(__name__)

# How long a row can sit in ``processing`` before we consider it orphaned.
# Long enough that a genuinely slow handler isn't re-run, short enough
# that a crashed worker's work is retried quickly.
ORPHAN_CUTOFF = timedelta(minutes=5)

# Cap orphan pickup per startup to avoid a thundering herd after a long
# outage. Anything over this stays for the next restart or a human to
# inspect.
ORPHAN_BATCH_LIMIT = 100


async def route_update(data: dict) -> None:
    """Dispatch one Telegram update to the right handler.

    Opens a fresh ``AsyncSession`` — the webhook's session is long gone
    by the time this runs in a background task. Commits on success,
    rolls back on exception (the caller marks the row status).
    """
    # Imports are local to avoid a module-import cycle with routers/
    # and to keep worker startup cheap (handlers pull in Telegram SDK
    # HTTP clients which open sockets on import).
    from backend.bot.handlers import asset_entry as asset_entry_handlers
    from backend.bot.handlers import briefing as briefing_handlers
    from backend.bot.handlers import onboarding as onboarding_handlers
    from backend.bot.handlers import storytelling as storytelling_handlers
    from backend.bot.handlers.callbacks import handle_transaction_callback
    from backend.bot.handlers.menu_handler import (
        handle_menu_callback as handle_menu_v2_callback,
    )
    from backend.bot.handlers.message import (
        handle_report_callback,
        handle_report_command,
        handle_text_message,
    )
    from backend.bot.personality.onboarding_flow import OnboardingStep
    from backend.services import dashboard_service
    from backend.services.telegram_service import (
        answer_callback,
        handle_menu_callback,
    )
    from backend import analytics

    update_id = data.get("update_id")
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            user_id = None
            message = data.get("message")
            if message:
                user_id = await _handle_message(
                    db, message,
                    onboarding_handlers=onboarding_handlers,
                    asset_entry_handlers=asset_entry_handlers,
                    storytelling_handlers=storytelling_handlers,
                    dashboard_service=dashboard_service,
                    handle_report_command=handle_report_command,
                    handle_text_message=handle_text_message,
                    OnboardingStep=OnboardingStep,
                    analytics=analytics,
                )
            else:
                callback_query = data.get("callback_query")
                if callback_query:
                    user_id = await _handle_callback(
                        db, callback_query,
                        onboarding_handlers=onboarding_handlers,
                        asset_entry_handlers=asset_entry_handlers,
                        briefing_handlers=briefing_handlers,
                        storytelling_handlers=storytelling_handlers,
                        dashboard_service=dashboard_service,
                        handle_transaction_callback=handle_transaction_callback,
                        handle_report_callback=handle_report_callback,
                        handle_menu_v2_callback=handle_menu_v2_callback,
                        handle_menu_callback=handle_menu_callback,
                        answer_callback=answer_callback,
                    )

            # Stamp the resolved user_id on the queue row so we can
            # replay / audit / delete updates per-user. Best-effort —
            # rows for unknown Telegram IDs stay with user_id NULL.
            if update_id is not None and user_id is not None:
                await db.execute(
                    sa_update(TelegramUpdate)
                    .where(TelegramUpdate.update_id == update_id)
                    .values(user_id=user_id)
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def _handle_message(
    db: AsyncSession,
    message: dict,
    *,
    onboarding_handlers,
    asset_entry_handlers,
    storytelling_handlers,
    dashboard_service,
    handle_report_command,
    handle_text_message,
    OnboardingStep,
    analytics,
):
    """Dispatch a message update. Returns the resolved internal user_id
    (or None if the sender isn't yet registered) so ``route_update`` can
    stamp it on the telegram_updates row.
    """
    text = message.get("text", "")
    chat_id = message["chat"]["id"]
    command = text.strip().lower()
    from_user = message.get("from") or {}
    telegram_id = from_user.get("id")

    if command == "/start":
        if telegram_id is None:
            analytics.track(
                analytics.EventType.BOT_STARTED,
                properties={"has_telegram_id": False, "new_user": False},
            )
            return None

        user, created = await dashboard_service.get_or_create_user(
            db,
            telegram_id,
            first_name=from_user.get("first_name"),
            last_name=from_user.get("last_name"),
            username=from_user.get("username"),
        )
        analytics.track(
            analytics.EventType.BOT_STARTED,
            user_id=user.id,
            properties={
                "new_user": created,
                "is_onboarded": user.is_onboarded,
                "has_display_name": bool(user.display_name),
            },
        )
        await onboarding_handlers.resume_or_start(db, chat_id, user)
        return user.id

    if command in ("/menu", "menu"):
        # Phase 3.6 — new 5-category menu replaces the V1 flat 8-button.
        # Resolve user up front so the menu can adapt (Epic 2 wires the
        # wealth-level lookup; Epic 1 just needs ``display_name``).
        from backend.bot.handlers.menu_handler import cmd_menu

        resolved_user = (
            await dashboard_service.get_user_by_telegram_id(db, telegram_id)
            if telegram_id is not None
            else None
        )
        await cmd_menu(db, chat_id, resolved_user)
        return resolved_user.id if resolved_user else None

    if command == "/report":
        await handle_report_command(db, message)
        if telegram_id is not None:
            user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
            return user.id if user else None
        return None

    # Resolve the user once up front for the remaining text-message
    # paths — all of them need it (either to detect the onboarding step
    # or to stamp user_id on the queue row).
    resolved_user = None
    if telegram_id is not None:
        resolved_user = await dashboard_service.get_user_by_telegram_id(
            db, telegram_id
        )

    # /taisan — list all active assets for the user.
    if command == "/taisan":
        if resolved_user is not None:
            await asset_entry_handlers.list_assets(
                db, chat_id, resolved_user
            )
            return resolved_user.id
        return None

    # /assets — open the asset-entry wizard (Phase 3A).
    if command in ("/assets", "/asset", "/themtaisan"):
        if resolved_user is not None:
            await asset_entry_handlers.start_asset_wizard(
                db, chat_id, resolved_user
            )
            return resolved_user.id
        return None

    # /story or /kechuyen — open storytelling mode (Phase 3A Epic 3).
    if command in ("/story", "/kechuyen", "/kể_chuyện"):
        if resolved_user is not None:
            await storytelling_handlers.handle_storytelling_command(
                db, chat_id, resolved_user
            )
            return resolved_user.id
        return None

    # /huy or /cancel — escape hatch out of any active wizard. Tries the
    # asset wizard first; if that wasn't active, falls back to
    # storytelling. Either flow's text mode otherwise blocks NL parsing,
    # so the user needs a non-button way to bail.
    if command in ("/huy", "/cancel"):
        if resolved_user is not None:
            if not await asset_entry_handlers.cancel_wizard(
                db, chat_id, resolved_user
            ):
                await storytelling_handlers.cancel_storytelling(
                    db, chat_id, resolved_user
                )
            return resolved_user.id
        return None

    # Storytelling voice input — only meaningful while in storytelling
    # mode. Routed BEFORE the asset wizard text dispatch because voice
    # messages have no ``text`` field and would fall through otherwise.
    if (
        message.get("voice")
        and resolved_user is not None
        and (resolved_user.wizard_state or {}).get("flow")
        == storytelling_handlers.FLOW_STORYTELLING
    ):
        consumed = await storytelling_handlers.handle_storytelling_input(
            db, message
        )
        if consumed:
            return resolved_user.id

    # Phase 3.5 — voice OUTSIDE storytelling = free-form query. Runs
    # AFTER the storytelling branch so a user mid-story doesn't get
    # their voice misrouted; before the text fallthrough so plain
    # voice messages aren't ignored.
    if message.get("voice") and resolved_user is not None:
        from backend.bot.handlers.voice_query import handle_voice_query
        consumed = await handle_voice_query(db, message)
        if consumed:
            return resolved_user.id

    # Plain text during the onboarding name step must be consumed here —
    # otherwise the NL expense parser would try to parse the user's name
    # as a transaction.
    if (
        text
        and resolved_user is not None
        and not command.startswith("/")
        and resolved_user.onboarding_step == int(OnboardingStep.ASKING_NAME)
    ):
        consumed = await onboarding_handlers.handle_name_input(
            db, chat_id, resolved_user, text
        )
        if consumed:
            return resolved_user.id

    # Storytelling text input — runs before the asset wizard dispatch
    # because ``wizard_state`` is shared between flows; checking the
    # flow name keeps the two from stomping on each other.
    if (
        text
        and resolved_user is not None
        and not command.startswith("/")
        and (resolved_user.wizard_state or {}).get("flow")
        == storytelling_handlers.FLOW_STORYTELLING
    ):
        consumed = await storytelling_handlers.handle_storytelling_input(
            db, message
        )
        if consumed:
            return resolved_user.id

    # Asset-entry wizard mid-flow text input — must be consumed before
    # the NL expense parser tries to interpret "VCB 100 triệu" as a
    # transaction.
    if (
        text
        and resolved_user is not None
        and not command.startswith("/")
        and resolved_user.wizard_state
    ):
        consumed = await asset_entry_handlers.handle_asset_text_input(
            db, message
        )
        if consumed:
            return resolved_user.id

    # Natural-language message → NL expense parser / report intent / menu fallback.
    await handle_text_message(db, message)
    return resolved_user.id if resolved_user else None


async def _handle_callback(
    db: AsyncSession,
    callback_query: dict,
    *,
    onboarding_handlers,
    asset_entry_handlers,
    briefing_handlers,
    storytelling_handlers,
    dashboard_service,
    handle_transaction_callback,
    handle_report_callback,
    handle_menu_v2_callback,
    handle_menu_callback,
    answer_callback,
):
    """Dispatch a callback_query update. Returns the resolved internal
    user_id (or None) so ``route_update`` can stamp it on the
    telegram_updates row.
    """
    callback_data = callback_query.get("data", "")
    chat_id = callback_query["message"]["chat"]["id"]
    callback_id = callback_query["id"]
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")

    async def _resolved_user_id():
        if telegram_id is None:
            return None
        user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
        return user.id if user else None

    # Onboarding callbacks first — otherwise the menu-callback handler
    # would swallow them.
    if await onboarding_handlers.handle_onboarding_callback(db, callback_query):
        return await _resolved_user_id()

    # Asset-entry wizard callbacks (asset_add:*).
    if await asset_entry_handlers.handle_asset_callback(db, callback_query):
        return await _resolved_user_id()

    # Morning-briefing button taps (briefing:*). Handled before the
    # transaction router because the briefing keyboard sits on its own
    # message thread and never overlaps with transaction prefixes.
    if await briefing_handlers.handle_briefing_callback(db, callback_query):
        return await _resolved_user_id()

    # Storytelling confirmation taps (story:*). Routed before the
    # transaction router so the "story:" prefix doesn't collide with
    # generic per-transaction edit/delete callbacks.
    if await storytelling_handlers.handle_storytelling_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.5 intent callbacks (intent_confirm:*, intent_clarify:*,
    # followup:*). Routed before the transaction handler because
    # those prefixes are distinct and the user is mid-flow.
    if callback_data.startswith("intent_") or callback_data.startswith(
        "followup:"
    ):
        from backend.bot.handlers.message import handle_intent_callback
        await answer_callback(callback_id)
        if await handle_intent_callback(db, callback_query):
            return await _resolved_user_id()

    # Transaction callbacks handle their own answerCallbackQuery so users
    # get richer feedback.
    if await handle_transaction_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.6 menu callbacks (menu:main / menu:<category>[:<action>]).
    # Owns its own answerCallbackQuery + edit-in-place navigation.
    # Returns False for legacy V1 prefixes like ``menu:ocr`` / ``menu:report``
    # so they fall through to the original handlers below.
    if await handle_menu_v2_callback(db, callback_query):
        return await _resolved_user_id()

    await answer_callback(callback_id)

    # "Báo cáo" button → generate report immediately instead of showing help.
    if callback_data == "menu:report":
        await handle_report_callback(db, callback_query)
        return await _resolved_user_id()

    await handle_menu_callback(chat_id, callback_data)
    return await _resolved_user_id()


async def process_update_safely(update_id: int, data: dict) -> None:
    """Background-task wrapper — never raises.

    Marks the ``telegram_updates`` row as ``done`` on success, ``failed``
    on exception. Logs but swallows so a handler bug cannot kill the
    event loop or propagate to Telegram as a webhook error.
    """
    try:
        await route_update(data)
        await _mark_status(update_id, STATUS_DONE)
    except Exception as exc:  # noqa: BLE001 — we explicitly want to swallow.
        logger.exception("route_update failed: update_id=%s", update_id)
        await _mark_status(update_id, STATUS_FAILED, error=str(exc)[:2000])


async def _mark_status(
    update_id: int, status: str, *, error: str | None = None
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            await db.execute(
                sa_update(TelegramUpdate)
                .where(TelegramUpdate.update_id == update_id)
                .values(
                    status=status,
                    processed_at=datetime.utcnow(),
                    error_message=error,
                )
            )
            await db.commit()
        except Exception:
            # Status update is best-effort — don't mask the real error
            # (if any) the caller is trying to report.
            logger.exception("Failed to mark update_id=%s as %s", update_id, status)
            await db.rollback()


async def _claim_orphan(db: AsyncSession, update_id: int, cutoff: datetime) -> bool:
    """Atomically claim one stale 'processing' row for this worker.

    Bumps ``received_at`` to NOW() only if the row is still ``status
    = 'processing'`` AND older than ``cutoff``. The row-level lock
    taken during UPDATE serializes concurrent workers — only the first
    worker's UPDATE hits (rowcount 1), the rest see received_at
    already past the cutoff and their predicate fails (rowcount 0).

    Returns True if this worker claimed the row and should schedule
    processing, False if another worker got there first.
    """
    stmt = (
        sa_update(TelegramUpdate)
        .where(
            TelegramUpdate.update_id == update_id,
            TelegramUpdate.status == STATUS_PROCESSING,
            TelegramUpdate.received_at < cutoff,
        )
        .values(received_at=datetime.utcnow())
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount == 1


async def recover_orphaned_updates() -> int:
    """Re-enqueue updates stuck in ``processing`` from a prior run.

    Runs both at startup and on a recurring timer (see
    ``run_recovery_loop``) so rows that get stuck after the web server
    is already up — e.g. a worker OOMs mid-handler — still get picked
    up without waiting for the next deploy.

    Safe across multiple uvicorn workers: each candidate is atomically
    claimed via ``_claim_orphan`` before being scheduled, so exactly
    one worker dispatches each orphan. Caps the batch per pass to
    avoid thundering-herd scheduling after a long outage. Returns the
    number of tasks spawned.
    """
    cutoff = datetime.utcnow() - ORPHAN_CUTOFF
    session_factory = get_session_factory()

    spawned = 0
    async with session_factory() as db:
        stmt = (
            select(TelegramUpdate.update_id, TelegramUpdate.payload)
            .where(
                TelegramUpdate.status == STATUS_PROCESSING,
                TelegramUpdate.received_at < cutoff,
            )
            .order_by(TelegramUpdate.received_at.asc())
            .limit(ORPHAN_BATCH_LIMIT)
        )
        candidates = (await db.execute(stmt)).all()

        for update_id, payload in candidates:
            if await _claim_orphan(db, update_id, cutoff):
                asyncio.create_task(process_update_safely(update_id, payload))
                spawned += 1

    if spawned:
        logger.info(
            "Recovered %d orphaned Telegram update(s) (%d candidates inspected)",
            spawned, len(candidates),
        )
    return spawned


# How often the in-process recovery loop wakes up. Must be shorter than
# ORPHAN_CUTOFF so a freshly-stuck row is picked up within one cutoff
# window regardless of when it became stale. 2 min gives ~2.5x headroom.
RECOVERY_INTERVAL = 120  # seconds


async def run_recovery_loop(interval_seconds: int = RECOVERY_INTERVAL) -> None:
    """Long-running coroutine that periodically re-enqueues orphans.

    Started from the FastAPI lifespan. Exits cleanly on
    ``CancelledError`` (raised during shutdown). Any other exception is
    logged and the loop continues — recovery is advisory, a single bad
    pass shouldn't kill it.
    """
    logger.info("Orphan recovery loop started (interval=%ss)", interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await recover_orphaned_updates()
            except Exception:
                logger.exception("Orphan recovery pass failed; continuing loop")
    except asyncio.CancelledError:
        logger.info("Orphan recovery loop cancelled")
        raise
