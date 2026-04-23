"""Tests for the empathy-check hourly job (Issue #40).

Covers:
- Quiet-hours (22:00–07:00 Asia/Ho_Chi_Minh) — job bails out early.
- Daily cap — skips users already at the cap.
- Success path stamps ``empathy_fired`` and commits.
- Failed Telegram send leaves NO ``empathy_fired`` event, so the
  cooldown allows a retry on the next pass.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.bot.personality.empathy_engine import EmpathyTrigger
from backend.jobs import check_empathy_triggers
from backend.models.user import User


TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _make_user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 888
    u.display_name = "Minh"
    u.onboarding_skipped = False
    u.onboarding_completed_at = datetime.now(timezone.utc)
    u.is_active = True
    return u


class _FakeSession:
    """Stub that exposes the exact subset of AsyncSession the job calls."""
    def __init__(self):
        self.commit = AsyncMock()
        self.add = MagicMock()
        self.flush = AsyncMock()
        self.execute = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
class TestQuietHours:
    async def test_skips_at_22_00(self):
        """22:00 local is inside quiet hours — job exits immediately."""
        now = datetime(2026, 4, 23, 15, 0, tzinfo=timezone.utc)  # 22:00 HCM
        with patch(
            "backend.jobs.check_empathy_triggers.get_session_factory"
        ) as session_factory:
            await check_empathy_triggers.run_hourly_empathy_check(now=now)
        session_factory.assert_not_called()

    async def test_skips_at_03_00(self):
        now = datetime(2026, 4, 22, 20, 0, tzinfo=timezone.utc)  # 03:00 HCM next day
        with patch(
            "backend.jobs.check_empathy_triggers.get_session_factory"
        ) as session_factory:
            await check_empathy_triggers.run_hourly_empathy_check(now=now)
        session_factory.assert_not_called()

    async def test_runs_at_10_00_local(self):
        now = datetime(2026, 4, 23, 3, 0, tzinfo=timezone.utc)  # 10:00 HCM
        with patch(
            "backend.jobs.check_empathy_triggers.get_session_factory",
            return_value=lambda: _FakeSession(),
        ), patch(
            "backend.jobs.check_empathy_triggers.get_active_users",
            new_callable=AsyncMock, return_value=[],
        ):
            await check_empathy_triggers.run_hourly_empathy_check(now=now)


@pytest.mark.asyncio
class TestProcessUser:
    async def test_daily_cap_short_circuits(self):
        """User already at 2 messages today → skip without calling engine."""
        user = _make_user()
        now = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
        session = _FakeSession()

        with patch(
            "backend.jobs.check_empathy_triggers.get_session_factory",
            return_value=lambda: session,
        ), patch(
            "backend.bot.personality.empathy_engine.count_empathy_fired_today",
            new_callable=AsyncMock,
            return_value=check_empathy_triggers.MAX_EMPATHY_PER_USER_PER_DAY,
        ) as count_mock, patch(
            "backend.bot.personality.empathy_engine.check_all_triggers",
            new_callable=AsyncMock,
        ) as triggers_mock, patch(
            "backend.jobs.check_empathy_triggers.send_message",
            new_callable=AsyncMock,
        ) as send_mock:
            await check_empathy_triggers._process_user(user, now=now)

        count_mock.assert_awaited_once()
        triggers_mock.assert_not_awaited()
        send_mock.assert_not_awaited()

    async def test_failed_send_does_not_stamp_event(self):
        user = _make_user()
        now = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
        session = _FakeSession()

        trigger = EmpathyTrigger(
            name="large_transaction", priority=1,
            cooldown_days=1, context={"amount": "5,000,000đ"},
        )
        with patch(
            "backend.jobs.check_empathy_triggers.get_session_factory",
            return_value=lambda: session,
        ), patch(
            "backend.bot.personality.empathy_engine.count_empathy_fired_today",
            new_callable=AsyncMock, return_value=0,
        ), patch(
            "backend.bot.personality.empathy_engine.check_all_triggers",
            new_callable=AsyncMock, return_value=trigger,
        ), patch(
            "backend.bot.personality.empathy_engine.render_message",
            return_value="Hello",
        ), patch(
            "backend.bot.personality.empathy_engine.record_fired",
            new_callable=AsyncMock,
        ) as record_mock, patch(
            "backend.jobs.check_empathy_triggers.send_message",
            new_callable=AsyncMock, return_value=None,  # Failed send
        ):
            await check_empathy_triggers._process_user(user, now=now)

        record_mock.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_success_path_records_and_commits(self):
        user = _make_user()
        now = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
        session = _FakeSession()

        trigger = EmpathyTrigger(
            name="user_silent_7_days", priority=4,
            cooldown_days=14, context={"days_silent": 9},
        )
        with patch(
            "backend.jobs.check_empathy_triggers.get_session_factory",
            return_value=lambda: session,
        ), patch(
            "backend.bot.personality.empathy_engine.count_empathy_fired_today",
            new_callable=AsyncMock, return_value=0,
        ), patch(
            "backend.bot.personality.empathy_engine.check_all_triggers",
            new_callable=AsyncMock, return_value=trigger,
        ), patch(
            "backend.bot.personality.empathy_engine.render_message",
            return_value="Hello",
        ), patch(
            "backend.bot.personality.empathy_engine.record_fired",
            new_callable=AsyncMock,
        ) as record_mock, patch(
            "backend.jobs.check_empathy_triggers.send_message",
            new_callable=AsyncMock, return_value={"ok": True},
        ):
            await check_empathy_triggers._process_user(user, now=now)

        record_mock.assert_awaited_once()
        session.commit.assert_awaited_once()
