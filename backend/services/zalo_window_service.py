"""48h reply window + free-message quota accounting (Phase 5.0 #3.1).

Zalo lets an Official Account send *consulting* (CS) messages only inside
48 hours of the user's last inbound message, and only 8 of them per
window. Both ceilings are enforced on Zalo's side; this module is the
local ledger that stops us **before** we burn a rejection — a rejected
send still costs a round-trip, and on a reactive-first channel a silent
rejection reads to the user as the bot ignoring them.

Contract with the layer rules
-----------------------------
Flush-only. Nothing here calls ``db.commit()`` and nothing reads env.
The caller owns the transaction boundary — which matters more than usual
for :func:`reserve_send`, because the reservation is only load-bearing
once it is *committed*. See :mod:`backend.adapters.zalo_window_notifier`
for where that commit happens and why it belongs at the edge.

Why "reserve/release" instead of the ``record_outbound()`` named in the
phase doc
-----------------------------------------------------------------------
A single ``record_outbound()`` called *after* a successful send cannot
hold the ceiling: eight concurrent sends would all read 7, all pass, and
all deliver. So the count is claimed *before* the HTTP call, in one
atomic ``UPDATE ... WHERE free_msg_count < 8 RETURNING``, and given back
by :func:`release_send` when the transport — not the quota — is what
failed.

That ordering is deliberate about which way it errs. If the process dies
between the reservation and the send, the slot is spent on a message
nobody received. That is the cheaper failure: *thà đếm dư 1 khi crash
giữa chừng còn hơn vượt trần thật* — over-counting costs one message out
of eight, over-sending costs the OA's standing with Zalo.

Concurrency note
----------------
The ceiling holds because of how Postgres evaluates a conflicting
``UPDATE`` under READ COMMITTED: the second writer blocks on the row
lock, then re-reads the committed row and re-checks the ``WHERE`` clause
before applying its own change. At ``free_msg_count = 7`` exactly one of
two racing reservations can therefore succeed. This is only true while
each send holds a **separate transaction** — riding a caller's long
session would hold the lock for the whole handler and serialise (or
deadlock) everything else touching the row.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.zalo_message_window import (
    FREE_MESSAGE_QUOTA,
    WINDOW_HOURS,
    ZaloMessageWindow,
)

logger = logging.getLogger(__name__)

# Why a send was (or wasn't) allowed. Stable strings — #3.3 emits them as
# a log field and a counter label, so renaming one breaks a dashboard.
REASON_OK = "ok"
REASON_NO_WINDOW = "no_window"
REASON_WINDOW_CLOSED = "window_closed"
REASON_QUOTA_EXHAUSTED = "quota_exhausted"

# Two more blocked-send reasons that this module never *produces* — both
# are transport facts the notifier discovers: the OA has no usable
# credential on this server, and the send failed after the client had
# already exhausted its own retries.
#
# They live here anyway, next to the three above, because #3.3 needs one
# closed vocabulary and only one place can own it. The alternative had
# :mod:`backend.services.zalo_quota_metrics` importing constants from an
# adapter to group its counters, which runs the layer contract backwards
# — services do not import adapters. The adapter re-exports these instead,
# which is the direction that is already allowed.
REASON_NOT_CONFIGURED = "not_configured"
REASON_SEND_FAILED = "send_failed"

# Every value that may appear as the ``reason`` field of a blocked-send
# log line or counter. Grouping in the metrics service is keyed on this
# tuple, so a reason invented at a call site lands in a bucket no
# dashboard and no runbook knows to look for.
BLOCK_REASONS = (
    REASON_NO_WINDOW,
    REASON_WINDOW_CLOSED,
    REASON_QUOTA_EXHAUSTED,
    REASON_NOT_CONFIGURED,
    REASON_SEND_FAILED,
)

# How long a reservation may sit unsettled before a window rotation stops
# carrying it and writes it off.
#
# Every reservation is settled — delivered, refused or refunded — as soon
# as the OA call returns, so a live one is only ever seconds old. The
# ones this bound exists for are the reservations nobody will ever settle:
# the process died between the reserve and the send. Without a cut-off
# those accumulate in ``inflight_count`` forever and eventually mute the
# sender permanently, which is a worse failure than the over-send the
# carry-over prevents.
#
# Five minutes is comfortably past the OA client's own timeout-plus-retry
# budget, so it can only ever write off a send that is genuinely gone.
INFLIGHT_GRACE = timedelta(minutes=5)

__all__ = [
    "BLOCK_REASONS",
    "FREE_MESSAGE_QUOTA",
    "INFLIGHT_GRACE",
    "REASON_NOT_CONFIGURED",
    "REASON_NO_WINDOW",
    "REASON_OK",
    "REASON_QUOTA_EXHAUSTED",
    "REASON_SEND_FAILED",
    "REASON_WINDOW_CLOSED",
    "WINDOW_HOURS",
    "Reservation",
    "WindowState",
    "bind_user",
    "can_send",
    "mask_zalo_id",
    "record_inbound",
    "release_send",
    "reserve_send",
    "settle_send",
]


@dataclass(frozen=True)
class WindowState:
    """Read-only view of one sender's window. Observability only.

    Deliberately *not* a gate: anything that branches on this and then
    sends has a race between the check and the send. Use
    :func:`reserve_send`, whose answer and whose side effect are the same
    statement.
    """

    allowed: bool
    reason: str
    free_msg_count: int
    remaining: int
    window_expires_at: datetime | None


@dataclass(frozen=True)
class Reservation:
    """Outcome of claiming one slot in the current window.

    ``window_expires_at`` records *which* window the slot came from. It
    no longer gates the refund — a slot still in flight is carried into
    whatever window replaces it, so that is exactly where its refund
    belongs — but it is what lets a release log line say which window it
    was compensating.
    """

    granted: bool
    reason: str
    free_msg_count: int
    window_expires_at: datetime | None

    @property
    def remaining(self) -> int:
        return max(0, FREE_MESSAGE_QUOTA - self.free_msg_count)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    """Postgres returns tz-aware values; hand-built rows may not be."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def record_inbound(
    db: AsyncSession,
    *,
    zalo_user_id: str,
    user_id: UUID | None = None,
    now: datetime | None = None,
) -> datetime:
    """Open (or re-open) the 48h window for ``zalo_user_id``.

    Every inbound message restarts the clock *and* the allowance —
    ``free_msg_count`` is reset, not incremented. That is Zalo's own
    semantics: the eight consulting messages are per window, and a new
    user message starts a new window.

    **Reset to the sends still in flight, not to 0.** A send that has
    claimed a slot but whose OA request has not come back yet can still
    succeed, and Zalo will charge it to whichever window it lands in —
    this one. Zeroing the counter under it hands the sender a full eight
    on top of a message already on the wire, which is the one thing this
    table exists to prevent. So the rotation carries ``inflight_count``
    across into both counters and leaves the settled sends behind.

    That carry-over is bounded by :data:`INFLIGHT_GRACE`: a reservation
    older than the OA client could plausibly still be working on is one
    whose process died before it could settle, and rotation is where it
    gets written off. Without the bound a single crash would ratchet the
    floor up and eventually mute the sender for good.

    ``user_id`` is coalesced rather than assigned so re-opening a window
    can never unlink an already-bound sender: an unlinked inbound
    (``user_id=None``) leaves an existing binding alone.

    **Monotonic.** The window only ever moves forward: an inbound whose
    ``now`` is not newer than the stored ``last_inbound_at`` leaves the
    row untouched. Both replay paths depend on this. Orphan recovery
    re-processes an event minutes after the fact, and Zalo itself
    re-delivers a webhook whose 200 we were too slow to return — in both
    cases the message was already accounted for, and re-applying it would
    extend a 48h window past its real expiry *and* hand back the free
    messages already spent inside it. Zalo's own counter would not move,
    so the next send would be rejected by Zalo while our ledger still
    believed it had room, which is precisely the drift this table exists
    to prevent.

    Returns the ``window_expires_at`` that is actually stored afterwards —
    the new one when the row advanced, the pre-existing one when the
    inbound was stale — so a caller can log the truth without a second
    read.
    """
    moment = now or _now()
    expires_at = moment + timedelta(hours=WINDOW_HOURS)

    # "This inbound is newer than what we have." A NULL ``last_inbound_at``
    # counts as newer: the row exists but has never seen a message, so
    # there is no window to protect.
    is_newer = or_(
        ZaloMessageWindow.last_inbound_at.is_(None),
        ZaloMessageWindow.last_inbound_at < moment,
    )

    # What survives the reset: reservations recent enough that the OA
    # call behind them could still be running. Anything older is a
    # reservation nobody is coming back to settle, and rotation is the
    # garbage collector for those.
    carried = case(
        (
            and_(
                ZaloMessageWindow.last_sent_at.is_not(None),
                ZaloMessageWindow.last_sent_at > moment - INFLIGHT_GRACE,
            ),
            ZaloMessageWindow.inflight_count,
        ),
        else_=0,
    )

    stmt = pg_insert(ZaloMessageWindow).values(
        zalo_user_id=zalo_user_id,
        user_id=user_id,
        last_inbound_at=moment,
        window_expires_at=expires_at,
        free_msg_count=0,
        inflight_count=0,
        created_at=moment,
        updated_at=moment,
    )
    stmt = (
        stmt.on_conflict_do_update(
            index_elements=[ZaloMessageWindow.zalo_user_id],
            set_={
                "last_inbound_at": case(
                    (is_newer, moment), else_=ZaloMessageWindow.last_inbound_at
                ),
                "window_expires_at": case(
                    (is_newer, expires_at), else_=ZaloMessageWindow.window_expires_at
                ),
                # Both counters land on the same carried value: after a
                # rotation the only sends the new window knows about are
                # the ones still on the wire, and every one of those is
                # both spent and unsettled. The invariant
                # ``inflight_count <= free_msg_count`` holds by
                # construction from here on.
                "free_msg_count": case(
                    (is_newer, carried), else_=ZaloMessageWindow.free_msg_count
                ),
                "inflight_count": case(
                    (is_newer, carried), else_=ZaloMessageWindow.inflight_count
                ),
                # Bumped unconditionally: we did see this row, and an
                # ``updated_at`` that lies about that makes a replay
                # invisible to anyone reading the table during an incident.
                "updated_at": moment,
                # COALESCE(incoming, existing): binds on first sight, never
                # clears an existing binding on a later anonymous inbound.
                # Not gated on ``is_newer`` — learning who a sender is can
                # never be the wrong direction, whatever the timestamp says.
                "user_id": func.coalesce(
                    stmt.excluded.user_id, ZaloMessageWindow.user_id
                ),
            },
        )
        .returning(ZaloMessageWindow.window_expires_at)
        .execution_options(synchronize_session=False)
    )
    stored = (await db.execute(stmt)).scalar_one_or_none()
    await db.flush()
    # ``stored`` is None only if the statement somehow matched nothing;
    # DO UPDATE always writes a row here, so falling back to ``expires_at``
    # is a belt-and-braces default rather than a real branch.
    return _as_utc(stored) or expires_at


async def bind_user(
    db: AsyncSession,
    *,
    zalo_user_id: str,
    user_id: UUID,
    now: datetime | None = None,
) -> bool:
    """Attach a resolved account to an existing window row.

    Called after the handler has worked out who the sender is (linking
    can complete *during* the message that opened the window). Only
    fills a NULL — a sender whose id already maps to an account is not
    re-pointed here; that is what the linking flow is for.

    Returns ``True`` when a row was actually bound.
    """
    moment = now or _now()
    result = await db.execute(
        update(ZaloMessageWindow)
        .where(
            ZaloMessageWindow.zalo_user_id == zalo_user_id,
            ZaloMessageWindow.user_id.is_(None),
        )
        .values(user_id=user_id, updated_at=moment)
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    return bool(result.rowcount)


async def reserve_send(
    db: AsyncSession,
    *,
    zalo_user_id: str,
    now: datetime | None = None,
) -> Reservation:
    """Claim one free-message slot, atomically.

    The whole decision is a single statement — increment guarded by both
    ceilings, returning the post-increment count. There is no window
    between deciding and spending, so two callers cannot both take the
    eighth slot.

    On refusal a second, read-only query classifies *why* (no window vs.
    expired vs. exhausted). That read is for the log line and the
    counter only; it never changes the outcome, so its being a moment
    stale is harmless.

    The caller must commit before performing the send. An uncommitted
    reservation holds a row lock and is invisible to every other worker,
    which is exactly the over-send this function exists to prevent.

    Every granted reservation must be closed out afterwards — by
    :func:`settle_send` when the OA answered either way, or by
    :func:`release_send` when the request never reached it. One that is
    left open survives a window rotation (that is the point) until
    :data:`INFLIGHT_GRACE` writes it off.
    """
    moment = now or _now()

    result = await db.execute(
        update(ZaloMessageWindow)
        .where(
            ZaloMessageWindow.zalo_user_id == zalo_user_id,
            ZaloMessageWindow.window_expires_at > moment,
            ZaloMessageWindow.free_msg_count < FREE_MESSAGE_QUOTA,
        )
        .values(
            free_msg_count=ZaloMessageWindow.free_msg_count + 1,
            # The slot is spent *and* unsettled until the OA answers.
            # ``last_sent_at`` is what dates it, so the two move together.
            inflight_count=ZaloMessageWindow.inflight_count + 1,
            last_sent_at=moment,
            updated_at=moment,
        )
        .returning(
            ZaloMessageWindow.free_msg_count,
            ZaloMessageWindow.window_expires_at,
        )
        # No ORM instance of this table is ever held across the call, and
        # 'auto' would try to reconcile the identity map through the same
        # RETURNING clause we are already using for the count.
        .execution_options(synchronize_session=False)
    )
    row = result.first()
    await db.flush()

    if row is not None:
        return Reservation(
            granted=True,
            reason=REASON_OK,
            free_msg_count=row.free_msg_count,
            window_expires_at=_as_utc(row.window_expires_at),
        )

    state = await can_send(db, zalo_user_id=zalo_user_id, now=moment)
    return Reservation(
        granted=False,
        reason=state.reason,
        free_msg_count=state.free_msg_count,
        window_expires_at=state.window_expires_at,
    )


async def settle_send(
    db: AsyncSession,
    *,
    zalo_user_id: str,
    now: datetime | None = None,
) -> bool:
    """Close out a reservation the OA has answered. Keeps the slot spent.

    Called for both answers, because both mean the same thing to this
    counter: the message reached Zalo, so it is charged to the window it
    was reserved in and no longer needs protecting from a rotation.
    A delivery keeps its slot because it was delivered; a rejection keeps
    its slot because Zalo may well have counted the attempt (see
    :mod:`backend.adapters.zalo_window_notifier` on why refunding those
    would let a rejected sender loop against our own ceiling).

    Deliberately **not** guarded on window identity. A reservation that
    survived a rotation lives in the new window now; keying the settle on
    the window it was born in would leave it unsettled forever, and an
    ``inflight_count`` that only ever goes up eventually mutes the sender.
    The ``> 0`` floor is what makes a replayed settle harmless instead.

    Returns ``True`` when a reservation was actually closed out.
    """
    moment = now or _now()
    result = await db.execute(
        update(ZaloMessageWindow)
        .where(
            ZaloMessageWindow.zalo_user_id == zalo_user_id,
            ZaloMessageWindow.inflight_count > 0,
        )
        .values(
            inflight_count=ZaloMessageWindow.inflight_count - 1,
            updated_at=moment,
        )
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    settled = bool(result.rowcount)
    if not settled:
        # Nothing left to settle: a rotation already wrote this
        # reservation off as abandoned, or the settle was replayed. Both
        # are benign, but only a log line tells them apart later.
        logger.info(
            "zalo.window.settle_noop zalo_user=%s",
            mask_zalo_id(zalo_user_id),
        )
    return settled


async def release_send(
    db: AsyncSession,
    *,
    zalo_user_id: str,
    window_expires_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Give back a slot whose send never reached Zalo.

    Guarded on ``inflight_count > 0`` rather than on window identity.
    The two used to be the same question — a rotation zeroed the counter,
    so refunding into a newer window would have manufactured allowance
    out of nothing. Now that a reservation is *carried* across the
    rotation, the new window is precisely where its refund belongs, and
    the identity guard would strand the slot instead. ``inflight_count``
    is the honest test: it counts reservations that are still open, in
    whichever window is holding them.

    ``free_msg_count > 0`` keeps the counter off negative if a release is
    somehow replayed; the invariant ``inflight_count <= free_msg_count``
    makes it redundant, and it stays as the cheaper of the two ways to
    find out the invariant broke.

    Not called when Zalo itself answered and refused — that is
    :func:`settle_send`, and the slot stays spent.

    ``window_expires_at`` is no longer a predicate; it identifies the
    reservation in the log line when there is nothing to give back.

    Returns ``True`` when a slot was actually returned.
    """
    if window_expires_at is None:
        return False

    moment = now or _now()
    result = await db.execute(
        update(ZaloMessageWindow)
        .where(
            ZaloMessageWindow.zalo_user_id == zalo_user_id,
            ZaloMessageWindow.inflight_count > 0,
            ZaloMessageWindow.free_msg_count > 0,
        )
        .values(
            free_msg_count=ZaloMessageWindow.free_msg_count - 1,
            inflight_count=ZaloMessageWindow.inflight_count - 1,
            updated_at=moment,
        )
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    released = bool(result.rowcount)
    if not released:
        # Expected when a rotation already wrote the reservation off as
        # abandoned; worth a line because the alternative cause — a double
        # release — is a bug and looks identical from here.
        logger.info(
            "zalo.window.release_noop zalo_user=%s window=%s",
            mask_zalo_id(zalo_user_id),
            window_expires_at.isoformat(),
        )
    return released


async def can_send(
    db: AsyncSession,
    *,
    zalo_user_id: str,
    now: datetime | None = None,
) -> WindowState:
    """Report whether a send *would* be allowed. Never gates one.

    Exists for logging, the ops runbook and tests. Production code that
    branches on this before sending has reintroduced the race
    :func:`reserve_send` removes — the only safe reading is "why did the
    reservation fail", after the fact.
    """
    moment = now or _now()
    row = (
        await db.execute(
            select(
                ZaloMessageWindow.free_msg_count,
                ZaloMessageWindow.window_expires_at,
            ).where(ZaloMessageWindow.zalo_user_id == zalo_user_id)
        )
    ).first()

    if row is None:
        return WindowState(
            allowed=False,
            reason=REASON_NO_WINDOW,
            free_msg_count=0,
            remaining=0,
            window_expires_at=None,
        )

    expires_at = _as_utc(row.window_expires_at)
    used = row.free_msg_count or 0
    remaining = max(0, FREE_MESSAGE_QUOTA - used)

    if expires_at is None or expires_at <= moment:
        return WindowState(
            allowed=False,
            reason=REASON_WINDOW_CLOSED,
            free_msg_count=used,
            remaining=remaining,
            window_expires_at=expires_at,
        )

    if used >= FREE_MESSAGE_QUOTA:
        return WindowState(
            allowed=False,
            reason=REASON_QUOTA_EXHAUSTED,
            free_msg_count=used,
            remaining=0,
            window_expires_at=expires_at,
        )

    return WindowState(
        allowed=True,
        reason=REASON_OK,
        free_msg_count=used,
        remaining=remaining,
        window_expires_at=expires_at,
    )


def mask_zalo_id(zalo_user_id: str) -> str:
    """Zalo user ids are pseudonymous but still identify a person.

    Logs keep enough to correlate two lines about the same sender and
    not enough to address them.

    Public because the quota decision is logged from two places — here,
    and in :mod:`backend.adapters.zalo_window_notifier` where the block
    actually happens. One masking rule, so two lines about the same
    sender still join up.
    """
    if len(zalo_user_id) <= 4:
        return "***"
    return f"{zalo_user_id[:2]}***{zalo_user_id[-2:]}"
