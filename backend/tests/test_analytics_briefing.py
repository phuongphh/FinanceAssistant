"""Tests for the morning-briefing analytics helpers in
``backend/analytics.py``:

- ``briefing_open_rate``
- ``briefing_open_rate_by_level``
- ``briefing_avg_time_to_open``

Reviewer flagged on PR #87 — these queries feed the
P3A-25 success criterion ("≥5/7 test users open briefing ≥5/7 days")
so coverage is non-negotiable.

The DB layer is mocked: each test feeds the function an explicit
``execute`` script rather than spinning up Postgres. That keeps the
tests fast and avoids needing a JSONB-aware test DB. The Python-side
windowing logic in ``briefing_avg_time_to_open`` is exercised in
detail since that's where the actual computation lives.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend import analytics
from backend.analytics import (
    BRIEFING_OPEN_WINDOW_SECONDS,
    briefing_avg_time_to_open,
    briefing_open_rate,
    briefing_open_rate_by_level,
)


def _scalar_result(value):
    """Build a result proxy whose ``.scalar()`` returns ``value``.

    Mirrors the call shape in ``briefing_open_rate``:
    ``int((await db.execute(stmt)).scalar() or 0)``.
    """
    proxy = MagicMock()
    proxy.scalar.return_value = value
    return proxy


def _all_result(rows):
    proxy = MagicMock()
    proxy.all.return_value = rows
    return proxy


# ── briefing_open_rate ───────────────────────────────────────────────


class TestBriefingOpenRate:
    @pytest.mark.asyncio
    async def test_zero_sent_returns_rate_zero_no_division(self):
        db = MagicMock()
        # Sent count = 0, opened count = 0
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0), _scalar_result(0),
        ])
        result = await briefing_open_rate(db)
        assert result == {"sent": 0, "opened": 0, "rate": 0.0}

    @pytest.mark.asyncio
    async def test_normal_operation(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(100),  # sent
            _scalar_result(45),   # opened
        ])
        result = await briefing_open_rate(db)
        assert result == {"sent": 100, "opened": 45, "rate": 0.45}

    @pytest.mark.asyncio
    async def test_rate_rounded_to_four_decimals(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(7),
            _scalar_result(3),
        ])
        result = await briefing_open_rate(db)
        # 3/7 = 0.428571... → 0.4286
        assert result["rate"] == 0.4286

    @pytest.mark.asyncio
    async def test_none_scalar_treated_as_zero(self):
        """COUNT(*) returns 0 not NULL but defensive code uses ``or 0``."""
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(None), _scalar_result(None),
        ])
        result = await briefing_open_rate(db)
        assert result == {"sent": 0, "opened": 0, "rate": 0.0}

    @pytest.mark.asyncio
    async def test_since_filter_passed_to_both_queries(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(10), _scalar_result(5),
        ])
        since = datetime(2026, 4, 1, tzinfo=timezone.utc)
        result = await briefing_open_rate(db, since=since)
        assert result["rate"] == 0.5
        # Both queries should have been issued
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_level_filter_passed_to_both_queries(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(20), _scalar_result(10),
        ])
        result = await briefing_open_rate(db, level="starter")
        assert result == {"sent": 20, "opened": 10, "rate": 0.5}


# ── briefing_open_rate_by_level ──────────────────────────────────────


class TestBriefingOpenRateByLevel:
    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_dict(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_all_result([]))
        result = await briefing_open_rate_by_level(db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_multi_level_buckets_assembled_correctly(self):
        """SQL groups by (level, event_type); function pivots into
        per-level dicts with sent / opened / rate."""
        rows = [
            ("starter", analytics.EventType.MORNING_BRIEFING_SENT, 100),
            ("starter", analytics.EventType.MORNING_BRIEFING_OPENED, 60),
            ("young_prof", analytics.EventType.MORNING_BRIEFING_SENT, 50),
            ("young_prof", analytics.EventType.MORNING_BRIEFING_OPENED, 30),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_all_result(rows))

        result = await briefing_open_rate_by_level(db)
        assert result == {
            "starter": {"sent": 100, "opened": 60, "rate": 0.6},
            "young_prof": {"sent": 50, "opened": 30, "rate": 0.6},
        }

    @pytest.mark.asyncio
    async def test_level_with_sends_no_opens_yields_zero_rate(self):
        rows = [
            ("hnw", analytics.EventType.MORNING_BRIEFING_SENT, 5),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_all_result(rows))

        result = await briefing_open_rate_by_level(db)
        assert result == {"hnw": {"sent": 5, "opened": 0, "rate": 0.0}}

    @pytest.mark.asyncio
    async def test_level_with_opens_no_sends_skips_division(self):
        """Hypothetical: opens without sends (data corruption) shouldn't
        ZeroDivisionError. ``rate`` falls back to 0.0."""
        rows = [
            ("starter", analytics.EventType.MORNING_BRIEFING_OPENED, 3),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_all_result(rows))

        result = await briefing_open_rate_by_level(db)
        assert result == {"starter": {"sent": 0, "opened": 3, "rate": 0.0}}

    @pytest.mark.asyncio
    async def test_null_level_bucketed_as_unknown(self):
        rows = [
            (None, analytics.EventType.MORNING_BRIEFING_SENT, 4),
            (None, analytics.EventType.MORNING_BRIEFING_OPENED, 2),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_all_result(rows))

        result = await briefing_open_rate_by_level(db)
        assert result == {"unknown": {"sent": 4, "opened": 2, "rate": 0.5}}

    @pytest.mark.asyncio
    async def test_since_filter_does_not_break_query(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_all_result([]))
        since = datetime(2026, 4, 1, tzinfo=timezone.utc)
        result = await briefing_open_rate_by_level(db, since=since)
        assert result == {}


# ── briefing_avg_time_to_open ────────────────────────────────────────


class TestBriefingAvgTimeToOpen:
    """The Python-side windowing logic — the most likely place for a
    subtle bug to land. Each test pins one branch."""

    def _setup(self, sent_rows, opened_rows):
        """Build a db whose two ``execute`` calls return the sent
        rows and then the opened rows (in that order, matching the
        function's call sequence)."""
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _all_result(sent_rows),
            _all_result(opened_rows),
        ])
        return db

    @pytest.mark.asyncio
    async def test_no_sent_events_returns_none(self):
        db = self._setup([], [])
        assert await briefing_avg_time_to_open(db) is None

    @pytest.mark.asyncio
    async def test_no_opened_events_returns_none(self):
        uid = uuid.uuid4()
        sent = [(uid, datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc))]
        db = self._setup(sent, [])
        assert await briefing_avg_time_to_open(db) is None

    @pytest.mark.asyncio
    async def test_opens_with_no_matching_user_returns_none(self):
        """User A sent a briefing, user B opened one — no pair, no avg."""
        a, b = uuid.uuid4(), uuid.uuid4()
        sent = [(a, datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc))]
        opened = [(b, datetime(2026, 4, 26, 7, 5, tzinfo=timezone.utc))]
        db = self._setup(sent, opened)
        assert await briefing_avg_time_to_open(db) is None

    @pytest.mark.asyncio
    async def test_single_pair_returns_delta_in_seconds(self):
        uid = uuid.uuid4()
        sent_at = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        opened_at = sent_at + timedelta(minutes=5)
        db = self._setup([(uid, sent_at)], [(uid, opened_at)])

        result = await briefing_avg_time_to_open(db)
        assert result == 300.0  # 5 minutes = 300 seconds

    @pytest.mark.asyncio
    async def test_open_outside_window_breaks_without_credit(self):
        """An open that arrives 45 min after send (window is 30 min)
        is the FIRST open for that send — break out without crediting,
        and don't fall through to look at later opens."""
        uid = uuid.uuid4()
        sent_at = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        late_open = sent_at + timedelta(minutes=45)
        db = self._setup([(uid, sent_at)], [(uid, late_open)])

        assert await briefing_avg_time_to_open(db) is None

    @pytest.mark.asyncio
    async def test_open_before_send_is_skipped(self):
        """An open that predates the send (e.g. tap on yesterday's
        briefing) should ``continue``, not ``break`` — the next open
        in the list might still qualify for THIS send."""
        uid = uuid.uuid4()
        sent_at = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        stale_open = sent_at - timedelta(minutes=10)  # before send
        valid_open = sent_at + timedelta(minutes=3)
        db = self._setup(
            [(uid, sent_at)],
            [(uid, stale_open), (uid, valid_open)],
        )

        result = await briefing_avg_time_to_open(db)
        assert result == 180.0  # 3 minutes

    @pytest.mark.asyncio
    async def test_only_first_qualifying_open_per_send_counts(self):
        """A user who taps the briefing 3 times within the window
        should only contribute ONE delta (the first tap)."""
        uid = uuid.uuid4()
        sent_at = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        opens = [
            (uid, sent_at + timedelta(minutes=2)),
            (uid, sent_at + timedelta(minutes=5)),
            (uid, sent_at + timedelta(minutes=10)),
        ]
        db = self._setup([(uid, sent_at)], opens)

        result = await briefing_avg_time_to_open(db)
        # First open after send is at +2min = 120s. Subsequent opens
        # don't widen the average.
        assert result == 120.0

    @pytest.mark.asyncio
    async def test_averages_across_multiple_users(self):
        """Two users, each with their own send+open. Average is the
        arithmetic mean of the two deltas."""
        a, b = uuid.uuid4(), uuid.uuid4()
        sent_a = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        sent_b = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        open_a = sent_a + timedelta(minutes=2)   # 120s
        open_b = sent_b + timedelta(minutes=8)   # 480s

        db = self._setup(
            [(a, sent_a), (b, sent_b)],
            [(a, open_a), (b, open_b)],
        )

        result = await briefing_avg_time_to_open(db)
        assert result == 300.0  # (120 + 480) / 2

    @pytest.mark.asyncio
    async def test_opens_not_matched_to_a_send_are_dropped(self):
        """User has 1 send + 2 opens; only the first open within the
        window contributes. The orphan open doesn't pull the average."""
        uid = uuid.uuid4()
        sent_at = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        opens = [
            (uid, sent_at + timedelta(minutes=10)),  # qualifies for send
            (uid, sent_at + timedelta(hours=5)),     # orphan — no second send
        ]
        db = self._setup([(uid, sent_at)], opens)

        result = await briefing_avg_time_to_open(db)
        assert result == 600.0  # 10 minutes only

    @pytest.mark.asyncio
    async def test_user_id_none_rows_are_skipped(self):
        """Old rows from before user_id was reliably populated must
        not crash the function or contribute to deltas."""
        uid = uuid.uuid4()
        sent_at = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        opens = [
            (None, sent_at + timedelta(minutes=1)),  # dropped
            (uid, sent_at + timedelta(minutes=4)),
        ]
        sent = [
            (None, sent_at - timedelta(minutes=5)),  # dropped
            (uid, sent_at),
        ]
        db = self._setup(sent, opens)

        result = await briefing_avg_time_to_open(db)
        assert result == 240.0  # only the (uid, +4min) pair counts

    @pytest.mark.asyncio
    async def test_window_boundary_at_exactly_30_minutes_qualifies(self):
        """Boundary check: delta == window is INCLUDED (``<=`` not ``<``)."""
        uid = uuid.uuid4()
        sent_at = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        boundary = sent_at + timedelta(seconds=BRIEFING_OPEN_WINDOW_SECONDS)
        db = self._setup([(uid, sent_at)], [(uid, boundary)])

        result = await briefing_avg_time_to_open(db)
        assert result == float(BRIEFING_OPEN_WINDOW_SECONDS)

    @pytest.mark.asyncio
    async def test_window_boundary_one_second_past_does_not_qualify(self):
        uid = uuid.uuid4()
        sent_at = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        past = sent_at + timedelta(seconds=BRIEFING_OPEN_WINDOW_SECONDS + 1)
        db = self._setup([(uid, sent_at)], [(uid, past)])

        result = await briefing_avg_time_to_open(db)
        assert result is None

    @pytest.mark.asyncio
    async def test_result_rounded_to_one_decimal(self):
        """Two pairs whose mean has a fractional second."""
        a, b = uuid.uuid4(), uuid.uuid4()
        t = datetime(2026, 4, 26, 7, 0, tzinfo=timezone.utc)
        db = self._setup(
            [(a, t), (b, t)],
            [(a, t + timedelta(seconds=10)),
             (b, t + timedelta(seconds=11))],
        )

        result = await briefing_avg_time_to_open(db)
        # (10 + 11) / 2 = 10.5
        assert result == 10.5
