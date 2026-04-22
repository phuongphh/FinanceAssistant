"""Unit tests for milestone_service detection rules.

Covers the three active detection paths and their edge cases:
- `_check_time_milestones`: days-since-created thresholds + timezone
  handling when `user.created_at` is naive.
- `_check_first_transaction`: triggers only after the first expense,
  dedup against existing rows.
- `_check_streak_milestones`: uses `longest_streak` as the watermark.
- IntegrityError fallback in `_create_if_missing` when two workers
  race to insert the same (user_id, milestone_type) row.

`AsyncSession.execute` returns a chain of awaitables and scalars; we
use small fake result objects so tests stay readable.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.user_milestone import MilestoneType
from backend.services import milestone_service


def _fake_user(created_at: datetime | None):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.created_at = created_at
    u.display_name = "Minh"
    u.get_greeting_name.return_value = "Minh"
    return u


def _fake_streak(current: int, longest: int):
    s = MagicMock()
    s.current_streak = current
    s.longest_streak = longest
    s.last_active_date = date.today()
    return s


def _fake_execute_rows(rows: list[tuple]):
    """Build a mock result where .all() returns the given rows."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _fake_execute_scalar(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


# -- _check_time_milestones ------------------------------------------

@pytest.mark.asyncio
class TestCheckTimeMilestones:
    async def test_returns_empty_when_user_missing(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        assert await milestone_service._check_time_milestones(
            db, uuid.uuid4()
        ) == []

    async def test_returns_empty_when_created_at_none(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=_fake_user(created_at=None))
        assert await milestone_service._check_time_milestones(
            db, uuid.uuid4()
        ) == []

    async def test_no_threshold_reached_yet(self):
        user = _fake_user(created_at=datetime.now(timezone.utc) - timedelta(days=3))
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._check_time_milestones(db, user.id)
        assert out == []
        db.add.assert_not_called()

    async def test_creates_days_7_milestone(self):
        user = _fake_user(
            created_at=datetime.now(timezone.utc) - timedelta(days=10)
        )
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        # No existing milestones.
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._check_time_milestones(db, user.id)
        assert len(out) == 1
        assert out[0].milestone_type == MilestoneType.DAYS_7
        assert out[0].extra["days"] == 10

    async def test_skips_thresholds_already_recorded(self):
        user = _fake_user(
            created_at=datetime.now(timezone.utc) - timedelta(days=40)
        )
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(
            return_value=_fake_execute_rows([(MilestoneType.DAYS_7,)])
        )
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._check_time_milestones(db, user.id)
        # Days_7 already recorded — only days_30 should be inserted.
        types = [m.milestone_type for m in out]
        assert MilestoneType.DAYS_7 not in types
        assert MilestoneType.DAYS_30 in types

    async def test_handles_naive_created_at(self):
        """Timezone-naive timestamps must be coerced to UTC, not crash."""
        naive_ts = datetime.utcnow() - timedelta(days=400)
        user = _fake_user(created_at=naive_ts)
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._check_time_milestones(db, user.id)
        # 400 days crosses all 4 thresholds.
        assert len(out) == 4


# -- _check_first_transaction ----------------------------------------

@pytest.mark.asyncio
class TestCheckFirstTransaction:
    async def test_skips_when_already_recorded(self):
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=_fake_execute_rows(
                [(MilestoneType.FIRST_TRANSACTION,)]
            )
        )
        out = await milestone_service._check_first_transaction(db, uuid.uuid4())
        assert out == []

    async def test_skips_when_no_expenses_yet(self):
        db = MagicMock()
        # First execute → existing_types query; second → count query.
        db.execute = AsyncMock(side_effect=[
            _fake_execute_rows([]),
            _fake_execute_scalar(0),
        ])
        out = await milestone_service._check_first_transaction(db, uuid.uuid4())
        assert out == []

    async def test_creates_milestone_after_first_expense(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _fake_execute_rows([]),      # existing_types
            _fake_execute_scalar(3),      # count expenses
        ])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._check_first_transaction(db, uuid.uuid4())
        assert len(out) == 1
        assert out[0].milestone_type == MilestoneType.FIRST_TRANSACTION
        assert out[0].extra["count"] == 3


# -- _check_streak_milestones ----------------------------------------

@pytest.mark.asyncio
class TestCheckStreakMilestones:
    async def test_returns_empty_when_no_streak_row(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        out = await milestone_service._check_streak_milestones(
            db, uuid.uuid4()
        )
        assert out == []

    async def test_no_threshold_below_7(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=_fake_streak(current=5, longest=5))
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._check_streak_milestones(
            db, uuid.uuid4()
        )
        assert out == []

    async def test_celebrates_longest_not_current(self):
        # User had a 40-day streak then broke it — they should still
        # get credit for 7 and 30 via longest_streak.
        db = MagicMock()
        db.get = AsyncMock(return_value=_fake_streak(current=1, longest=40))
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._check_streak_milestones(
            db, uuid.uuid4()
        )
        types = [m.milestone_type for m in out]
        assert MilestoneType.STREAK_7 in types
        assert MilestoneType.STREAK_30 in types
        assert MilestoneType.STREAK_100 not in types

    async def test_all_three_at_100(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=_fake_streak(current=100, longest=100))
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._check_streak_milestones(
            db, uuid.uuid4()
        )
        types = [m.milestone_type for m in out]
        assert set(types) == {
            MilestoneType.STREAK_7,
            MilestoneType.STREAK_30,
            MilestoneType.STREAK_100,
        }


# -- concurrency / IntegrityError ------------------------------------

@pytest.mark.asyncio
class TestCreateIfMissing:
    async def test_integrity_error_does_not_raise(self):
        """Concurrent workers: DB unique constraint wins, we rollback
        and return None instead of propagating the error."""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock(
            side_effect=IntegrityError("stmt", {}, Exception("dup"))
        )
        db.rollback = AsyncMock()
        db.refresh = AsyncMock()

        out = await milestone_service._create_if_missing(
            db, uuid.uuid4(), MilestoneType.DAYS_7,
        )
        assert out is None
        db.rollback.assert_awaited_once()

    async def test_existing_set_shortcircuits_without_db_write(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        existing = {MilestoneType.DAYS_7}

        out = await milestone_service._create_if_missing(
            db, uuid.uuid4(), MilestoneType.DAYS_7, existing=existing,
        )
        assert out is None
        db.add.assert_not_called()
        db.commit.assert_not_awaited()
