"""Tests for the morning briefing scheduler.

Focus on the documented edge cases from issue #70:

- 15-minute window math (incl. midnight wrap)
- already_sent_today dedup uses the user's local day, not UTC
- failed Notifier send leaves the user dedup-eligible for retry
- per-user error doesn't stop the loop
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend import analytics
from backend.bot.formatters.briefing_formatter import BriefingResult
from backend.jobs import morning_briefing_job as job
from backend.models.user import User
from backend.wealth.ladder import WealthLevel


VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _make_user(*, telegram_id: int = 100, briefing_time: time = time(7, 0)) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = telegram_id
    u.display_name = "Minh"
    u.briefing_enabled = True
    u.briefing_time = briefing_time
    u.expense_threshold_micro = 200_000
    u.is_active = True
    u.deleted_at = None
    return u


# ── _is_within_15_min ────────────────────────────────────────────────


class TestIsWithin15Min:
    def test_inside_window_at_boundary(self):
        assert job._is_within_15_min(time(7, 0), time(7, 0)) is True

    def test_inside_window_late(self):
        assert job._is_within_15_min(time(7, 14), time(7, 0)) is True

    def test_outside_window(self):
        assert job._is_within_15_min(time(7, 15), time(7, 0)) is False

    def test_before_window(self):
        assert job._is_within_15_min(time(6, 59), time(7, 0)) is False

    def test_midnight_wrap_target_2355_now_0005(self):
        """target=23:55 covers up to 00:10 — 00:05 is 10 min after target."""
        assert job._is_within_15_min(time(0, 5), time(23, 55)) is True

    def test_midnight_wrap_target_2355_now_0011(self):
        assert job._is_within_15_min(time(0, 11), time(23, 55)) is False


# ── already_sent_today ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_already_sent_today_returns_false_when_no_event():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: None))
    user_id = uuid.uuid4()
    now = datetime(2026, 4, 26, 7, 0, tzinfo=VN)
    sent = await job.already_sent_today(db, user_id, now=now)
    assert sent is False


@pytest.mark.asyncio
async def test_already_sent_today_returns_true_when_event_exists():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: ("row",)))
    user_id = uuid.uuid4()
    now = datetime(2026, 4, 26, 7, 0, tzinfo=VN)
    sent = await job.already_sent_today(db, user_id, now=now)
    assert sent is True


# ── run_morning_briefing_job ─────────────────────────────────────────


def _patch_session_factory():
    """Stand-up a minimal session factory whose AsyncSession context
    returns a MagicMock the test can attach an AsyncMock execute to.
    """
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    class _Sess:
        async def __aenter__(self): return db
        async def __aexit__(self, *a): pass

    return lambda: _Sess(), db


@pytest.mark.asyncio
async def test_skips_users_outside_window():
    user = _make_user(briefing_time=time(8, 0))
    factory, _ = _patch_session_factory()

    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value={"ok": True})

    with patch(
        "backend.jobs.morning_briefing_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.morning_briefing_job._get_briefing_candidates",
        new=AsyncMock(return_value=[user]),
    ), patch(
        "backend.jobs.morning_briefing_job.get_notifier",
        return_value=notifier,
    ), patch(
        "backend.jobs.morning_briefing_job.asyncio.sleep",
        new=AsyncMock(),
    ):
        # Now is 7:00 — 1 hour before the user's briefing_time of 8:00.
        sent = await job.run_morning_briefing_job(
            now=datetime(2026, 4, 26, 7, 0, tzinfo=VN),
        )

    assert sent == 0
    notifier.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_dedup_skips_already_sent_user():
    user = _make_user(briefing_time=time(7, 0))
    factory, _ = _patch_session_factory()

    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value={"ok": True})

    with patch(
        "backend.jobs.morning_briefing_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.morning_briefing_job._get_briefing_candidates",
        new=AsyncMock(return_value=[user]),
    ), patch(
        "backend.jobs.morning_briefing_job.already_sent_today",
        new=AsyncMock(return_value=True),
    ), patch(
        "backend.jobs.morning_briefing_job.get_notifier",
        return_value=notifier,
    ), patch(
        "backend.jobs.morning_briefing_job.asyncio.sleep",
        new=AsyncMock(),
    ):
        sent = await job.run_morning_briefing_job(
            now=datetime(2026, 4, 26, 7, 5, tzinfo=VN),
        )

    assert sent == 0
    notifier.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_sends_and_tracks_when_eligible():
    user = _make_user(briefing_time=time(7, 0))
    factory, _ = _patch_session_factory()

    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value={"ok": True, "result": {}})

    formatter_result = BriefingResult(
        text="🌅 Sáng Minh ơi", level=WealthLevel.STARTER, char_count=18,
    )

    with patch(
        "backend.jobs.morning_briefing_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.morning_briefing_job._get_briefing_candidates",
        new=AsyncMock(return_value=[user]),
    ), patch(
        "backend.jobs.morning_briefing_job.already_sent_today",
        new=AsyncMock(return_value=False),
    ), patch(
        "backend.jobs.morning_briefing_job.BriefingFormatter.generate_for_user",
        new=AsyncMock(return_value=formatter_result),
    ), patch(
        "backend.jobs.morning_briefing_job.get_notifier",
        return_value=notifier,
    ), patch(
        "backend.jobs.morning_briefing_job.analytics.atrack",
        new=AsyncMock(),
    ) as atrack_mock, patch(
        "backend.jobs.morning_briefing_job.asyncio.sleep",
        new=AsyncMock(),
    ):
        sent = await job.run_morning_briefing_job(
            now=datetime(2026, 4, 26, 7, 5, tzinfo=VN),
        )

    assert sent == 1
    notifier.send_message.assert_awaited_once()
    # Analytics row carries level for the funnel breakdown.
    atrack_mock.assert_awaited_once()
    args, kwargs = atrack_mock.await_args
    assert args[0] == analytics.EventType.MORNING_BRIEFING_SENT
    assert kwargs["user_id"] == user.id
    assert kwargs["properties"]["level"] == "starter"


@pytest.mark.asyncio
async def test_failed_send_does_not_track_sent_event():
    """Notifier returning None must NOT log MORNING_BRIEFING_SENT —
    otherwise dedup blocks the retry next run.
    """
    user = _make_user(briefing_time=time(7, 0))
    factory, _ = _patch_session_factory()

    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value=None)

    formatter_result = BriefingResult(
        text="x", level=WealthLevel.STARTER, char_count=1,
    )

    with patch(
        "backend.jobs.morning_briefing_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.morning_briefing_job._get_briefing_candidates",
        new=AsyncMock(return_value=[user]),
    ), patch(
        "backend.jobs.morning_briefing_job.already_sent_today",
        new=AsyncMock(return_value=False),
    ), patch(
        "backend.jobs.morning_briefing_job.BriefingFormatter.generate_for_user",
        new=AsyncMock(return_value=formatter_result),
    ), patch(
        "backend.jobs.morning_briefing_job.get_notifier",
        return_value=notifier,
    ), patch(
        "backend.jobs.morning_briefing_job.analytics.atrack",
        new=AsyncMock(),
    ) as atrack_mock, patch(
        "backend.jobs.morning_briefing_job.asyncio.sleep",
        new=AsyncMock(),
    ):
        sent = await job.run_morning_briefing_job(
            now=datetime(2026, 4, 26, 7, 5, tzinfo=VN),
        )

    assert sent == 0
    atrack_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_user_failure_does_not_halt_others():
    """When the formatter raises for user 1, user 2 still gets sent."""
    bad = _make_user(telegram_id=100)
    good = _make_user(telegram_id=200)
    factory, _ = _patch_session_factory()

    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value={"ok": True})

    async def fake_generate(self, db, user):
        if user.id == bad.id:
            raise RuntimeError("boom")
        return BriefingResult(
            text="ok", level=WealthLevel.STARTER, char_count=2,
        )

    with patch(
        "backend.jobs.morning_briefing_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.morning_briefing_job._get_briefing_candidates",
        new=AsyncMock(return_value=[bad, good]),
    ), patch(
        "backend.jobs.morning_briefing_job.already_sent_today",
        new=AsyncMock(return_value=False),
    ), patch(
        "backend.jobs.morning_briefing_job.BriefingFormatter.generate_for_user",
        new=fake_generate,
    ), patch(
        "backend.jobs.morning_briefing_job.get_notifier",
        return_value=notifier,
    ), patch(
        "backend.jobs.morning_briefing_job.analytics.atrack",
        new=AsyncMock(),
    ), patch(
        "backend.jobs.morning_briefing_job.asyncio.sleep",
        new=AsyncMock(),
    ):
        sent = await job.run_morning_briefing_job(
            now=datetime(2026, 4, 26, 7, 5, tzinfo=VN),
        )

    assert sent == 1
    assert notifier.send_message.await_count == 1
