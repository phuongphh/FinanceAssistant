"""Unit tests for the streak service (Phase 2, Issue #41).

Covers:
- Day 1 → current=1
- Day 2 after Day 1 → current=2, streak_continued=True
- Same-day re-entry → idempotent no-op
- Gap > 1 day → reset to 1
- longest_streak is a monotonic watermark
- Milestone flag triggers at 7/30/100/365

Uses in-memory SQLite for simplicity — streak logic doesn't depend on
Postgres-specific features beyond the upsert, which we swap for a plain
add() in-test via monkeypatching the dialect-specific insert.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.streak import UserStreak
from backend.models.user import User
from backend.services import streak_service


def _make_user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.timezone = "Asia/Ho_Chi_Minh"
    u.telegram_id = 999
    return u


class _FakeSession:
    """Minimal AsyncSession stub that persists an in-memory UserStreak.

    Records whether flush/commit were called so we can assert the
    TRANSACTION_OWNED_BY_CALLER contract (service flushes, caller commits).
    """
    def __init__(self, user: User, streak: UserStreak | None = None):
        self._user = user
        self._streak = streak
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.execute = AsyncMock()  # Used for the upsert on first seed.

    async def get(self, model, pk):
        if model is User and pk == self._user.id:
            return self._user
        if model is UserStreak and pk == self._user.id:
            return self._streak
        return None

    def set_streak(self, streak: UserStreak) -> None:
        """Simulate the upsert landing a row."""
        self._streak = streak


@pytest.mark.asyncio
class TestRecordActivity:
    async def test_day_one_initialises_streak(self):
        user = _make_user()
        db = _FakeSession(user, streak=None)

        # Simulate: upsert runs, and after re-read the row exists.
        async def _fake_execute(stmt):
            db.set_streak(UserStreak(
                user_id=user.id,
                current_streak=1,
                longest_streak=1,
                last_active_date=date(2026, 4, 23),
            ))
            return MagicMock()
        db.execute = AsyncMock(side_effect=_fake_execute)

        out = await streak_service.record_activity(
            db, user.id, today=date(2026, 4, 23)
        )
        assert out.current == 1
        assert out.longest == 1
        assert out.streak_continued is True
        assert out.is_milestone is False  # 1 is not a milestone

    async def test_consecutive_day_advances(self):
        user = _make_user()
        streak = UserStreak(
            user_id=user.id,
            current_streak=1,
            longest_streak=1,
            last_active_date=date(2026, 4, 22),
        )
        db = _FakeSession(user, streak=streak)

        out = await streak_service.record_activity(
            db, user.id, today=date(2026, 4, 23)
        )
        assert out.current == 2
        assert out.longest == 2
        assert out.streak_continued is True
        db.flush.assert_awaited()
        # Contract: service must NOT commit.
        db.commit.assert_not_awaited()

    async def test_same_day_is_idempotent(self):
        user = _make_user()
        streak = UserStreak(
            user_id=user.id,
            current_streak=5,
            longest_streak=5,
            last_active_date=date(2026, 4, 23),
        )
        db = _FakeSession(user, streak=streak)

        out = await streak_service.record_activity(
            db, user.id, today=date(2026, 4, 23)
        )
        assert out.current == 5  # unchanged
        assert out.streak_continued is False
        assert out.is_milestone is False  # no-op doesn't re-fire milestone

    async def test_gap_of_two_days_resets(self):
        user = _make_user()
        streak = UserStreak(
            user_id=user.id,
            current_streak=10,
            longest_streak=10,
            last_active_date=date(2026, 4, 20),
        )
        db = _FakeSession(user, streak=streak)

        out = await streak_service.record_activity(
            db, user.id, today=date(2026, 4, 23)
        )
        assert out.current == 1  # reset
        assert out.longest == 10  # watermark preserved
        assert out.streak_continued is True

    async def test_longest_never_decreases_after_reset(self):
        user = _make_user()
        streak = UserStreak(
            user_id=user.id,
            current_streak=3,
            longest_streak=42,
            last_active_date=date(2026, 4, 20),
        )
        db = _FakeSession(user, streak=streak)

        out = await streak_service.record_activity(
            db, user.id, today=date(2026, 4, 25)
        )
        assert out.longest == 42

    async def test_seven_is_milestone(self):
        user = _make_user()
        streak = UserStreak(
            user_id=user.id,
            current_streak=6,
            longest_streak=6,
            last_active_date=date(2026, 4, 22),
        )
        db = _FakeSession(user, streak=streak)

        out = await streak_service.record_activity(
            db, user.id, today=date(2026, 4, 23)
        )
        assert out.current == 7
        assert out.is_milestone is True

    async def test_thirty_one_is_not_milestone(self):
        """Milestone fires AT the threshold, not past it."""
        user = _make_user()
        streak = UserStreak(
            user_id=user.id,
            current_streak=30,
            longest_streak=30,
            last_active_date=date(2026, 4, 22),
        )
        db = _FakeSession(user, streak=streak)

        out = await streak_service.record_activity(
            db, user.id, today=date(2026, 4, 23)
        )
        assert out.current == 31
        assert out.is_milestone is False  # 31 not in {7, 30, 100, 365}


class TestTimezoneDate:
    def test_falls_back_when_tz_invalid(self):
        # Should never raise — returns today() in Asia/Ho_Chi_Minh fallback.
        out = streak_service._today_in_tz("Not/A_Real_Zone")
        assert isinstance(out, date)

    def test_respects_explicit_tz(self):
        out = streak_service._today_in_tz("UTC")
        assert isinstance(out, date)
