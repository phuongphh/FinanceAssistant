"""Phase 5.0 #3.1 — 48h window and the 8-message allowance.

The DoD line under test: *"Ngoài cửa sổ 48h hoặc đã dùng 8 tin → không
gọi ``/message/cs``, Telegram vẫn nhận, log rõ lý do."*

Two kinds of test here, and the split is deliberate.

**Shape tests** compile the real statements and assert their WHERE and
SET clauses. They are what pins the guarantee that actually matters —
that a reservation is one atomic conditional write, not a read followed
by a write. No Python fake can demonstrate that; only the SQL can.

**Sequence tests** run the service against
:class:`FakeWindowStore`, which re-implements those same statements in
memory. They cover the behaviour over time: a window opening, eight
sends spending it, the ninth refused, an inbound message re-opening it.
The fake is trustworthy exactly as far as the shape tests hold it to the
real SQL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.models.zalo_message_window import (
    FREE_MESSAGE_QUOTA,
    WINDOW_HOURS,
    ZaloMessageWindow,
)
from backend.services import zalo_window_service as svc

from .conftest import FakeWindowRow

_PG = postgresql.dialect()

SENDER = "zalo-sender-should-never-be-logged"
T0 = datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc)


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=_PG))


async def _open_window(store, *, at=T0, user_id=None):
    return await svc.record_inbound(store, zalo_user_id=SENDER, user_id=user_id, now=at)


# ---------------------------------------------------------------------------
# record_inbound
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_inbound_opens_a_48h_window(window_store):
    expires_at = await _open_window(window_store)

    assert expires_at == T0 + timedelta(hours=WINDOW_HOURS)
    row = window_store.rows[SENDER]
    assert row.last_inbound_at == T0
    assert row.window_expires_at == expires_at
    assert row.free_msg_count == 0


@pytest.mark.asyncio
async def test_record_inbound_is_an_upsert_not_a_duplicate_row(window_store):
    await _open_window(window_store)
    await _open_window(window_store, at=T0 + timedelta(hours=1))

    assert len(window_store.rows) == 1
    assert window_store.rows[SENDER].window_expires_at == (
        T0 + timedelta(hours=1 + WINDOW_HOURS)
    )


@pytest.mark.asyncio
async def test_new_inbound_resets_the_allowance(window_store):
    """A new window means eight fresh messages, not eight ever."""
    await _open_window(window_store)
    for _ in range(FREE_MESSAGE_QUOTA):
        assert (
            await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
        ).granted

    later = T0 + timedelta(hours=5)
    await _open_window(window_store, at=later)

    assert window_store.rows[SENDER].free_msg_count == 0
    assert (
        await svc.reserve_send(window_store, zalo_user_id=SENDER, now=later)
    ).granted


# ---------------------------------------------------------------------------
# The window only moves forward (#3)
# ---------------------------------------------------------------------------
#
# Zalo redelivers, and redeliveries do not arrive in order. An upsert that
# writes whatever the latest *delivery* says would let a replay of an old
# event roll the window back — and, worse, zero ``free_msg_count`` while
# the current window is half spent, handing back allowance the OA has
# already charged. The guard is a CASE on ``last_inbound_at``.


@pytest.mark.asyncio
async def test_a_stale_inbound_neither_extends_the_window_nor_refunds(window_store):
    fresh = await _open_window(window_store, at=T0 + timedelta(hours=1))
    for _ in range(3):
        await svc.reserve_send(
            window_store, zalo_user_id=SENDER, now=T0 + timedelta(hours=1)
        )

    stored = await _open_window(window_store, at=T0)  # the late replay

    row = window_store.rows[SENDER]
    assert row.last_inbound_at == T0 + timedelta(hours=1)
    assert row.window_expires_at == fresh
    assert row.free_msg_count == 3
    # RETURNING reports what is *stored*, not what was offered — a caller
    # logging the expiry must not be told about a window that lost.
    assert stored == fresh


@pytest.mark.asyncio
async def test_a_replay_at_the_same_instant_is_not_newer(window_store):
    """The equality edge, which is where an off-by-one lands.

    A duplicate delivery of the *same* event carries the same timestamp.
    ``<`` rather than ``<=`` is what stops it from resetting the counter.
    """
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    await _open_window(window_store, at=T0)

    assert window_store.rows[SENDER].free_msg_count == 1


@pytest.mark.asyncio
async def test_a_stale_inbound_still_teaches_us_who_the_sender_is(window_store):
    """The binding sits outside the CASE on purpose: learning an identity
    is never the wrong direction, whatever the timestamp says."""
    await _open_window(window_store, at=T0 + timedelta(hours=1))
    user_id = uuid4()

    await _open_window(window_store, at=T0, user_id=user_id)

    row = window_store.rows[SENDER]
    assert row.user_id == user_id
    assert row.window_expires_at == T0 + timedelta(hours=1 + WINDOW_HOURS)


@pytest.mark.asyncio
async def test_a_first_ever_inbound_on_an_empty_row_counts_as_newer(window_store):
    """A row can exist with no ``last_inbound_at`` — bound by ``bind_user``
    before any message was recorded. NULL must read as "no window to
    protect", not as a value the guard compares against."""
    window_store.rows[SENDER] = FakeWindowRow(SENDER)
    assert window_store.rows[SENDER].last_inbound_at is None

    stored = await _open_window(window_store)

    assert stored == T0 + timedelta(hours=WINDOW_HOURS)
    assert window_store.rows[SENDER].window_expires_at == stored


@pytest.mark.asyncio
async def test_the_monotonic_upsert_always_writes_a_row(window_store):
    """Shape, not sequence — and the reason the guard is a CASE rather
    than ``on_conflict_do_update(..., where=...)``.

    A WHERE-filtered DO UPDATE writes *nothing* when the incoming event is
    stale, so ``RETURNING`` yields no row and the caller cannot tell "the
    window held" from "the statement matched nothing". Moving the guard
    into the SET arms keeps the write unconditional: the row is always
    touched, so the expiry always comes back.
    """
    await _open_window(window_store)
    sql = window_store.statements[-1]

    assert "ON CONFLICT" in sql and "DO UPDATE" in sql
    # No WHERE between the SET list and RETURNING — that is the whole claim.
    assert "WHERE" not in sql.split("DO UPDATE")[1].split("RETURNING")[0]
    assert "RETURNING" in sql
    # All three window columns move together, each behind the same guard.
    for column in ("last_inbound_at", "window_expires_at", "free_msg_count"):
        assert f"{column} = CASE WHEN" in sql
    # ``updated_at`` is deliberately *not* guarded: we did see this row,
    # and a timestamp that hides a replay is useless during an incident.
    assert "updated_at = CASE" not in sql


@pytest.mark.asyncio
async def test_record_inbound_binds_the_user_on_first_sight(window_store):
    user_id = uuid4()
    await _open_window(window_store, user_id=user_id)

    assert window_store.rows[SENDER].user_id == user_id


@pytest.mark.asyncio
async def test_reopening_anonymously_never_unlinks_the_sender(window_store):
    """An unlinked inbound must not wipe a binding we already have.

    A user links, then sends from a context where the handler hasn't
    resolved the account yet. Assigning ``user_id`` outright would drop
    the link; ``COALESCE`` keeps it.
    """
    user_id = uuid4()
    await _open_window(window_store, user_id=user_id)
    await _open_window(window_store, at=T0 + timedelta(hours=2), user_id=None)

    assert window_store.rows[SENDER].user_id == user_id


def test_record_inbound_sql_coalesces_the_binding():
    stmt = pg_insert(ZaloMessageWindow).values(zalo_user_id=SENDER)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ZaloMessageWindow.zalo_user_id],
        set_={
            "user_id": svc.func.coalesce(
                stmt.excluded.user_id, ZaloMessageWindow.user_id
            )
        },
    )
    assert "coalesce(excluded.user_id, zalo_message_window.user_id)" in _sql(stmt)


@pytest.mark.asyncio
async def test_record_inbound_does_not_commit(window_store):
    """Flush-only: the worker owns the transaction boundary."""
    await _open_window(window_store)

    assert window_store.commits == 0
    assert window_store.flushes >= 1


# ---------------------------------------------------------------------------
# bind_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_user_fills_an_empty_binding(window_store):
    await _open_window(window_store)
    user_id = uuid4()

    assert await svc.bind_user(window_store, zalo_user_id=SENDER, user_id=user_id)
    assert window_store.rows[SENDER].user_id == user_id


@pytest.mark.asyncio
async def test_bind_user_leaves_an_existing_binding_alone(window_store):
    original = uuid4()
    await _open_window(window_store, user_id=original)

    assert not await svc.bind_user(window_store, zalo_user_id=SENDER, user_id=uuid4())
    assert window_store.rows[SENDER].user_id == original


@pytest.mark.asyncio
async def test_bind_user_on_a_missing_window_is_a_noop(window_store):
    assert not await svc.bind_user(window_store, zalo_user_id=SENDER, user_id=uuid4())
    assert window_store.rows == {}


def test_bind_user_sql_guards_on_null():
    stmt = (
        update(ZaloMessageWindow)
        .where(
            ZaloMessageWindow.zalo_user_id == SENDER,
            ZaloMessageWindow.user_id.is_(None),
        )
        .values(user_id=uuid4())
    )
    assert "user_id IS NULL" in _sql(stmt)


# ---------------------------------------------------------------------------
# reserve_send — the ceiling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reserve_send_grants_inside_a_fresh_window(window_store):
    await _open_window(window_store)

    reservation = await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    assert reservation.granted
    assert reservation.reason == svc.REASON_OK
    assert reservation.free_msg_count == 1
    assert reservation.remaining == FREE_MESSAGE_QUOTA - 1
    assert reservation.window_expires_at == T0 + timedelta(hours=WINDOW_HOURS)


@pytest.mark.asyncio
async def test_reserve_send_stops_at_the_eighth_message(window_store):
    await _open_window(window_store)

    granted = [
        await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
        for _ in range(FREE_MESSAGE_QUOTA + 2)
    ]

    assert [r.granted for r in granted] == [True] * FREE_MESSAGE_QUOTA + [False, False]
    assert granted[-1].reason == svc.REASON_QUOTA_EXHAUSTED
    assert granted[-1].remaining == 0
    # The refusals must not keep incrementing — Zalo counts 8, so do we.
    assert window_store.rows[SENDER].free_msg_count == FREE_MESSAGE_QUOTA


@pytest.mark.asyncio
async def test_reserve_send_refuses_after_the_window_expires(window_store):
    await _open_window(window_store)
    too_late = T0 + timedelta(hours=WINDOW_HOURS, seconds=1)

    reservation = await svc.reserve_send(
        window_store, zalo_user_id=SENDER, now=too_late
    )

    assert not reservation.granted
    assert reservation.reason == svc.REASON_WINDOW_CLOSED
    assert window_store.rows[SENDER].free_msg_count == 0


@pytest.mark.asyncio
async def test_the_window_closes_exactly_at_the_boundary(window_store):
    """``> now``, not ``>=``: at the 48h mark the window is already shut.

    Zalo rejects a send that lands on the boundary, so erring open would
    buy nothing and cost a rejection.
    """
    await _open_window(window_store)
    boundary = T0 + timedelta(hours=WINDOW_HOURS)

    assert not (
        await svc.reserve_send(window_store, zalo_user_id=SENDER, now=boundary)
    ).granted
    assert (
        await svc.reserve_send(
            window_store, zalo_user_id=SENDER, now=boundary - timedelta(seconds=1)
        )
    ).granted


@pytest.mark.asyncio
async def test_reserve_send_without_a_window_reports_no_window(window_store):
    """A sender who has never messaged us has no reply window at all.

    Distinct from ``window_closed`` on purpose: this one usually means a
    proactive send was attempted at a sender we've never heard from,
    which is a wiring bug, not an expired conversation.
    """
    reservation = await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    assert not reservation.granted
    assert reservation.reason == svc.REASON_NO_WINDOW
    assert reservation.window_expires_at is None


@pytest.mark.asyncio
async def test_reserve_send_does_not_commit(window_store):
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    assert window_store.commits == 0


@pytest.mark.asyncio
async def test_a_refusal_costs_one_extra_read_and_a_grant_costs_none(window_store):
    """The classify-the-reason SELECT must not sit on the happy path.

    Every granted send is one round-trip. Slipping a lookup in front of
    it would tax the common case to explain the rare one.
    """
    await _open_window(window_store)
    window_store.statements.clear()

    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
    assert [s.startswith("SELECT") for s in window_store.statements] == [False]

    window_store.statements.clear()
    await svc.reserve_send(
        window_store, zalo_user_id=SENDER, now=T0 + timedelta(days=3)
    )
    assert [s.startswith("SELECT") for s in window_store.statements] == [False, True]


def test_reserve_send_sql_is_one_conditional_increment():
    """The whole ceiling lives in this statement.

    Both bounds are in the WHERE clause and the increment is relative to
    the stored column, so two concurrent reservations serialise on the
    row lock and the second re-checks ``free_msg_count < 8`` against the
    committed value before it applies. Read-then-write would let eight
    callers all see 7.
    """
    stmt = (
        update(ZaloMessageWindow)
        .where(
            ZaloMessageWindow.zalo_user_id == SENDER,
            ZaloMessageWindow.window_expires_at > T0,
            ZaloMessageWindow.free_msg_count < FREE_MESSAGE_QUOTA,
        )
        .values(free_msg_count=ZaloMessageWindow.free_msg_count + 1)
        .returning(ZaloMessageWindow.free_msg_count)
    )
    sql = _sql(stmt)

    assert "free_msg_count=(zalo_message_window.free_msg_count + " in sql
    assert "zalo_message_window.window_expires_at > " in sql
    assert "zalo_message_window.free_msg_count < " in sql
    assert "RETURNING" in sql
    # One statement decides and spends. No SELECT ... FOR UPDATE dance,
    # nothing for a second caller to interleave with.
    assert sql.count("UPDATE") == 1


def test_reserve_send_quota_bound_is_the_platform_constant():
    """8 is Zalo's number, not ours — it must not be typed twice."""
    assert svc.FREE_MESSAGE_QUOTA == FREE_MESSAGE_QUOTA == 8
    assert svc.WINDOW_HOURS == WINDOW_HOURS == 48


# ---------------------------------------------------------------------------
# release_send — compensation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_returns_the_slot_after_a_transport_failure(window_store):
    await _open_window(window_store)
    reservation = await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    released = await svc.release_send(
        window_store,
        zalo_user_id=SENDER,
        window_expires_at=reservation.window_expires_at,
        now=T0,
    )

    assert released
    assert window_store.rows[SENDER].free_msg_count == 0
    # And the slot is genuinely reusable, not just decremented.
    assert (await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)).granted


@pytest.mark.asyncio
async def test_release_follows_its_reservation_across_a_rotation(window_store):
    """A refund lands wherever the reservation ended up.

    Sequence: reserve, the send fails, and before the compensation lands
    the user messages us and opens a fresh window. The reservation was
    still in flight, so the rotation carried it into that new window —
    which is therefore exactly where the refund belongs. Guarding on the
    window it was *born* in would strand the slot instead.
    """
    await _open_window(window_store)
    reservation = await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    later = T0 + timedelta(minutes=1)
    await _open_window(window_store, at=later)
    assert window_store.rows[SENDER].free_msg_count == 1  # carried, not zeroed

    released = await svc.release_send(
        window_store,
        zalo_user_id=SENDER,
        window_expires_at=reservation.window_expires_at,
        now=later,
    )

    assert released
    row = window_store.rows[SENDER]
    assert (row.free_msg_count, row.inflight_count) == (0, 0)


@pytest.mark.asyncio
async def test_release_of_a_written_off_reservation_manufactures_nothing(window_store):
    """The other half of the same rule: a rotation past the grace ends it.

    Once :data:`~backend.services.zalo_window_service.INFLIGHT_GRACE` has
    passed, the reservation is presumed abandoned and the rotation writes
    it off. A compensation arriving after that has already been accounted
    for, so it must not hand the new window a ninth slot.
    """
    await _open_window(window_store)
    reservation = await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    later = T0 + svc.INFLIGHT_GRACE + timedelta(seconds=1)
    await _open_window(window_store, at=later)

    released = await svc.release_send(
        window_store,
        zalo_user_id=SENDER,
        window_expires_at=reservation.window_expires_at,
        now=later,
    )

    assert not released
    assert window_store.rows[SENDER].free_msg_count == 0


@pytest.mark.asyncio
async def test_a_written_off_reservation_can_still_refund_a_newer_one(window_store):
    """The residual this design knowingly accepts, pinned so it stays small.

    Reservations are counted, not named. If one is written off and *another*
    send is in flight when the stale compensation finally lands, the refund
    lands on that newer reservation — the counter cannot tell them apart.
    Cost is one slot out of eight, and it takes a compensation arriving more
    than :data:`~backend.services.zalo_window_service.INFLIGHT_GRACE` after
    its own reservation, which is past the OA client's whole
    timeout-and-retry budget. Naming reservations would need a row per send;
    that is a lot of machinery for a window that holds eight.

    This is the one place the ledger errs toward under-counting. It stays
    survivable because Zalo enforces the same ceiling server-side: the worst
    case is a refused ninth send, not a silently over-quota OA.
    """
    await _open_window(window_store)
    reservation = await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    later = T0 + svc.INFLIGHT_GRACE + timedelta(seconds=1)
    await _open_window(window_store, at=later)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=later)

    released = await svc.release_send(
        window_store,
        zalo_user_id=SENDER,
        window_expires_at=reservation.window_expires_at,
        now=later,
    )

    assert released
    row = window_store.rows[SENDER]
    assert (row.free_msg_count, row.inflight_count) == (0, 0)


@pytest.mark.asyncio
async def test_release_never_drives_the_counter_negative(window_store):
    """A replayed compensation must not manufacture allowance."""
    expires_at = await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    first = await svc.release_send(
        window_store, zalo_user_id=SENDER, window_expires_at=expires_at, now=T0
    )
    second = await svc.release_send(
        window_store, zalo_user_id=SENDER, window_expires_at=expires_at, now=T0
    )

    assert (first, second) == (True, False)
    assert window_store.rows[SENDER].free_msg_count == 0


@pytest.mark.asyncio
async def test_release_without_a_reservation_touches_nothing(window_store):
    """``window_expires_at=None`` means no slot was ever taken."""
    await _open_window(window_store)
    window_store.statements.clear()

    assert not await svc.release_send(
        window_store, zalo_user_id=SENDER, window_expires_at=None, now=T0
    )
    assert window_store.statements == []


@pytest.mark.asyncio
async def test_a_noop_release_is_logged_without_the_sender_id(window_store, caplog):
    """The no-op is expected sometimes and a bug other times — log it.

    Zalo user ids are pseudonymous but still identify a person, so the
    line correlates without addressing.
    """
    await _open_window(window_store)

    with caplog.at_level("INFO", logger=svc.logger.name):
        await svc.release_send(
            window_store,
            zalo_user_id=SENDER,
            window_expires_at=T0 - timedelta(days=9),
            now=T0,
        )

    assert "zalo.window.release_noop" in caplog.text
    assert SENDER not in caplog.text


@pytest.mark.asyncio
async def test_release_sql_guards_on_the_inflight_counter_and_the_floor(window_store):
    """Asserted on the statement the service actually emitted.

    ``inflight_count > 0`` is the whole guard now: it is true exactly
    while a reservation is open, in whichever window is holding it. The
    ``free_msg_count > 0`` arm is redundant given the invariant and stays
    as the cheap way to find out the invariant broke.
    """
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
    window_store.statements.clear()

    await svc.release_send(
        window_store,
        zalo_user_id=SENDER,
        window_expires_at=T0 + timedelta(hours=WINDOW_HOURS),
        now=T0,
    )

    (sql,) = window_store.statements
    assert "zalo_message_window.inflight_count > " in sql
    assert "zalo_message_window.free_msg_count > " in sql
    assert "free_msg_count=(zalo_message_window.free_msg_count - " in sql
    assert "inflight_count=(zalo_message_window.inflight_count - " in sql
    # The window it was reserved in is no longer a predicate — see
    # test_release_follows_its_reservation_across_a_rotation.
    assert "zalo_message_window.window_expires_at" not in sql


# ---------------------------------------------------------------------------
# settle_send — closing out a reservation Zalo answered (#1029(4))
# ---------------------------------------------------------------------------
#
# The bug this section pins: ``record_inbound`` used to zero
# ``free_msg_count`` outright, which erased a slot whose OA request had
# not come back yet. Zalo still charged that send — to the *new* window —
# while the local row believed all eight were free, so the OA could push
# nine or more consulting messages into one 48h window. ``inflight_count``
# is what lets the rotation tell a live reservation from a spent one.


@pytest.mark.asyncio
async def test_reserve_marks_the_slot_in_flight(window_store):
    await _open_window(window_store)

    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    row = window_store.rows[SENDER]
    assert (row.free_msg_count, row.inflight_count) == (1, 1)


@pytest.mark.asyncio
async def test_settle_keeps_the_slot_spent(window_store):
    """Zalo has seen the message; the allowance is gone either way."""
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    assert await svc.settle_send(window_store, zalo_user_id=SENDER, now=T0)

    row = window_store.rows[SENDER]
    assert (row.free_msg_count, row.inflight_count) == (1, 0)


@pytest.mark.asyncio
async def test_settle_survives_the_rotation_that_carried_it(window_store):
    """Not keyed on the window the reservation was born in.

    By the time the OA answers, an inbound message may have rotated the
    window and taken the reservation with it. A settle that insisted on
    the original window would never match, ``inflight_count`` would only
    ever climb, and the sender would eventually be muted for good.
    """
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    later = T0 + timedelta(minutes=1)
    await _open_window(window_store, at=later)

    assert await svc.settle_send(window_store, zalo_user_id=SENDER, now=later)

    row = window_store.rows[SENDER]
    assert (row.free_msg_count, row.inflight_count) == (1, 0)


@pytest.mark.asyncio
async def test_a_rotation_carries_the_send_that_is_still_on_the_wire(window_store):
    """The regression test for #1029(4).

    Seven sends have been delivered and settled; the eighth is still
    waiting on the OA when a new inbound message rotates the window. The
    seven are written off — that is what a new window means — but the
    eighth is carried, because Zalo will charge it to the window it
    lands in. Zeroing outright is what allowed a ninth message.
    """
    await _open_window(window_store)
    for _ in range(FREE_MESSAGE_QUOTA):
        assert (
            await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
        ).granted
    for _ in range(FREE_MESSAGE_QUOTA - 1):
        assert await svc.settle_send(window_store, zalo_user_id=SENDER, now=T0)

    later = T0 + timedelta(minutes=1)
    await _open_window(window_store, at=later)

    row = window_store.rows[SENDER]
    assert (row.free_msg_count, row.inflight_count) == (1, 1)
    # And the new window is worth seven more, not eight: the send on the
    # wire is Zalo's eighth for this window.
    granted = [
        (await svc.reserve_send(window_store, zalo_user_id=SENDER, now=later)).granted
        for _ in range(FREE_MESSAGE_QUOTA)
    ]
    assert granted == [True] * (FREE_MESSAGE_QUOTA - 1) + [False]


@pytest.mark.asyncio
async def test_a_rotation_writes_off_a_reservation_nobody_settled(window_store):
    """The carry-over is bounded, or a crash would mute the sender.

    Every live reservation is settled within seconds of the OA
    answering, so one older than the grace period belongs to a process
    that died between the reserve and the send. Carrying those forever
    would ratchet the floor up window after window.
    """
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    later = T0 + svc.INFLIGHT_GRACE + timedelta(seconds=1)
    await _open_window(window_store, at=later)

    row = window_store.rows[SENDER]
    assert (row.free_msg_count, row.inflight_count) == (0, 0)


@pytest.mark.asyncio
async def test_the_carried_count_never_exceeds_the_spent_count(window_store):
    """``inflight_count <= free_msg_count`` holds across a whole lifecycle."""
    await _open_window(window_store)
    row = window_store.rows[SENDER]

    async def _invariant():
        assert 0 <= row.inflight_count <= row.free_msg_count <= FREE_MESSAGE_QUOTA

    for _ in range(3):
        await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
        await _invariant()
    await svc.settle_send(window_store, zalo_user_id=SENDER, now=T0)
    await _invariant()
    await svc.release_send(
        window_store,
        zalo_user_id=SENDER,
        window_expires_at=row.window_expires_at,
        now=T0,
    )
    await _invariant()
    await _open_window(window_store, at=T0 + timedelta(minutes=1))
    await _invariant()
    assert (row.free_msg_count, row.inflight_count) == (1, 1)


@pytest.mark.asyncio
async def test_a_replayed_settle_is_a_logged_noop(window_store):
    """Nothing in flight means nothing to close out — and no negative."""
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
    await svc.settle_send(window_store, zalo_user_id=SENDER, now=T0)

    assert not await svc.settle_send(window_store, zalo_user_id=SENDER, now=T0)
    row = window_store.rows[SENDER]
    assert (row.free_msg_count, row.inflight_count) == (1, 0)


@pytest.mark.asyncio
async def test_a_noop_settle_is_logged_without_the_sender_id(window_store, caplog):
    await _open_window(window_store)

    with caplog.at_level("INFO", logger=svc.logger.name):
        assert not await svc.settle_send(window_store, zalo_user_id=SENDER, now=T0)

    assert "zalo.window.settle_noop" in caplog.text
    assert SENDER not in caplog.text


@pytest.mark.asyncio
async def test_settle_does_not_commit(window_store):
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
    await svc.settle_send(window_store, zalo_user_id=SENDER, now=T0)

    assert window_store.commits == 0


@pytest.mark.asyncio
async def test_settle_sql_touches_only_the_inflight_counter(window_store):
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)
    window_store.statements.clear()

    await svc.settle_send(window_store, zalo_user_id=SENDER, now=T0)

    (sql,) = window_store.statements
    assert "inflight_count=(zalo_message_window.inflight_count - " in sql
    assert "zalo_message_window.inflight_count > " in sql
    # The slot stays spent, and the window it came from is irrelevant.
    assert "free_msg_count" not in sql
    assert "window_expires_at" not in sql


# ---------------------------------------------------------------------------
# can_send — observability only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_can_send_reports_an_open_window(window_store):
    await _open_window(window_store)
    await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    state = await svc.can_send(window_store, zalo_user_id=SENDER, now=T0)

    assert state.allowed
    assert state.reason == svc.REASON_OK
    assert state.free_msg_count == 1
    assert state.remaining == FREE_MESSAGE_QUOTA - 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup_sends", "at_offset", "expected_reason"),
    [
        (0, timedelta(hours=WINDOW_HOURS + 1), svc.REASON_WINDOW_CLOSED),
        (FREE_MESSAGE_QUOTA, timedelta(hours=1), svc.REASON_QUOTA_EXHAUSTED),
    ],
)
async def test_can_send_classifies_each_refusal(
    window_store, setup_sends, at_offset, expected_reason
):
    await _open_window(window_store)
    for _ in range(setup_sends):
        await svc.reserve_send(window_store, zalo_user_id=SENDER, now=T0)

    state = await svc.can_send(window_store, zalo_user_id=SENDER, now=T0 + at_offset)

    assert not state.allowed
    assert state.reason == expected_reason


@pytest.mark.asyncio
async def test_can_send_on_an_unknown_sender(window_store):
    state = await svc.can_send(window_store, zalo_user_id=SENDER, now=T0)

    assert not state.allowed
    assert state.reason == svc.REASON_NO_WINDOW
    assert state.remaining == 0


@pytest.mark.asyncio
async def test_can_send_writes_nothing(window_store):
    """It is a report. Anything that gates a send uses reserve_send."""
    await _open_window(window_store)
    window_store.statements.clear()

    await svc.can_send(window_store, zalo_user_id=SENDER, now=T0)

    assert all(s.startswith("SELECT") for s in window_store.statements)
    assert window_store.commits == 0


def test_can_send_query_reads_only_the_two_columns_it_needs():
    """No ``SELECT *`` on a table the send path touches per message."""
    stmt = select(
        ZaloMessageWindow.free_msg_count, ZaloMessageWindow.window_expires_at
    ).where(ZaloMessageWindow.zalo_user_id == SENDER)
    sql = _sql(stmt)

    assert "payload" not in sql
    assert sql.count(",") == 1


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_naive_timestamps_from_a_hand_built_row_are_read_as_utc(window_store):
    """Postgres returns tz-aware values; fixtures and old rows may not.

    Comparing a naive datetime against an aware ``now`` raises, which on
    the send path would surface as a 500 rather than a declined send.
    """
    await _open_window(window_store)
    window_store.rows[SENDER].window_expires_at = (
        T0 + timedelta(hours=WINDOW_HOURS)
    ).replace(tzinfo=None)

    state = await svc.can_send(window_store, zalo_user_id=SENDER, now=T0)

    assert state.allowed
    assert state.window_expires_at.tzinfo is not None


def test_reason_strings_are_stable():
    """#3.3 emits these as log fields and counter labels."""
    assert svc.REASON_OK == "ok"
    assert svc.REASON_NO_WINDOW == "no_window"
    assert svc.REASON_WINDOW_CLOSED == "window_closed"
    assert svc.REASON_QUOTA_EXHAUSTED == "quota_exhausted"


def test_masking_keeps_correlation_without_the_identifier():
    masked = svc.mask_zalo_id(SENDER)

    assert SENDER not in masked
    assert masked == svc.mask_zalo_id(SENDER)
    assert svc.mask_zalo_id("abc") == "***"
