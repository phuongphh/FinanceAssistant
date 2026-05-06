"""Tests for ``backend.jobs.reminder_scheduler_job``.

We focus on the scheduler decision logic — which patterns get
pinged, when they get bundled, and the safeguards (snooze, already-
paid, last_reminder_sent today). The Telegram send + per-user
session lifecycle is covered by integration tests in a future phase.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.jobs import reminder_scheduler_job
from backend.models.recurring_pattern import RecurringPattern


def _pattern(
    *,
    user_id: uuid.UUID,
    name: str = "Thuê nhà",
    category: str = "housing",
    expected_amount: Decimal = Decimal("15000000"),
    expected_day: int = 5,
    enable_reminders: bool = True,
    is_active: bool = True,
    last_reminder_sent: date | None = None,
    snooze_until: date | None = None,
    last_occurrence_date: date | None = None,
) -> RecurringPattern:
    p = RecurringPattern()
    p.id = uuid.uuid4()
    p.user_id = user_id
    p.name = name
    p.category = category
    p.expected_amount = expected_amount
    p.amount_variance_pct = 10.0
    p.schedule_type = "monthly"
    p.expected_day_of_month = expected_day
    p.is_active = is_active
    p.enable_reminders = enable_reminders
    p.reminder_days_before = 2
    p.last_reminder_sent = last_reminder_sent
    p.snooze_until = snooze_until
    p.last_occurrence_date = last_occurrence_date
    p.occurrence_count = 0
    p.created_at = datetime.utcnow()
    return p


def _result_with_rows(rows):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    # was_paid_this_period uses scalar_one_or_none — without this
    # explicit None, MagicMock returns a truthy magic object and the
    # scheduler thinks every pattern was already paid.
    result.scalar_one_or_none.return_value = rows[0] if rows else None
    return result


def _mock_db(execute_returns):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_returns)
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
class TestLoadDuePatterns:
    async def test_due_today_is_picked_up(self):
        """Today=Apr 5, due_day=5 → days_until=0 ≤ days_before=2."""
        user_id = uuid.uuid4()
        p = _pattern(user_id=user_id, expected_day=5)
        db = _mock_db([
            _result_with_rows([p]),    # patterns
            _result_with_rows([]),     # was_paid_this_period — no expense
        ])
        result = await reminder_scheduler_job._load_due_patterns_by_user(
            db, today=date(2026, 4, 5),
        )
        assert user_id in result
        assert result[user_id] == [p]

    async def test_too_far_off_skipped(self):
        """Today=Apr 1, due_day=10 → 9 days away > 2 → skip."""
        user_id = uuid.uuid4()
        p = _pattern(user_id=user_id, expected_day=10)
        db = _mock_db([_result_with_rows([p])])
        result = await reminder_scheduler_job._load_due_patterns_by_user(
            db, today=date(2026, 4, 1),
        )
        assert result == {}

    async def test_snoozed_pattern_skipped(self):
        """Snooze-until in the future → skip."""
        user_id = uuid.uuid4()
        p = _pattern(
            user_id=user_id, expected_day=5,
            snooze_until=date(2026, 4, 10),
        )
        db = _mock_db([_result_with_rows([p])])
        result = await reminder_scheduler_job._load_due_patterns_by_user(
            db, today=date(2026, 4, 5),
        )
        assert result == {}

    async def test_already_reminded_today_skipped(self):
        user_id = uuid.uuid4()
        p = _pattern(
            user_id=user_id, expected_day=5,
            last_reminder_sent=date(2026, 4, 5),
        )
        db = _mock_db([_result_with_rows([p])])
        result = await reminder_scheduler_job._load_due_patterns_by_user(
            db, today=date(2026, 4, 5),
        )
        assert result == {}

    async def test_already_paid_skipped(self):
        """User paid via storytelling earlier today → skip ping."""
        user_id = uuid.uuid4()
        p = _pattern(user_id=user_id, expected_day=5)
        # Mock was_paid_this_period to return True (an Expense.id row).
        db = _mock_db([
            _result_with_rows([p]),
            _result_with_rows([uuid.uuid4()]),  # an expense matched
        ])
        # Patch the helper so its query returns True.
        with patch(
            "backend.services.recurring_service.was_paid_this_period",
            new=AsyncMock(return_value=True),
        ):
            result = await reminder_scheduler_job._load_due_patterns_by_user(
                db, today=date(2026, 4, 5),
            )
        assert result == {}


class TestFormatReminders:
    def test_single_today_formatting(self):
        p = _pattern(user_id=uuid.uuid4(), expected_day=5)
        text = reminder_scheduler_job._format_single_reminder(
            p, date(2026, 4, 5), today=date(2026, 4, 5),
        )
        assert "Hôm nay" in text
        assert "Thuê nhà" in text
        assert "15,000,000" in text

    def test_single_tomorrow_formatting(self):
        p = _pattern(user_id=uuid.uuid4(), expected_day=5)
        text = reminder_scheduler_job._format_single_reminder(
            p, date(2026, 4, 5), today=date(2026, 4, 4),
        )
        assert "Ngày mai" in text

    def test_single_2_days_away(self):
        p = _pattern(user_id=uuid.uuid4(), expected_day=5)
        text = reminder_scheduler_job._format_single_reminder(
            p, date(2026, 4, 5), today=date(2026, 4, 3),
        )
        assert "2 ngày nữa" in text

    def test_bundle_includes_total(self):
        user_id = uuid.uuid4()
        patterns = [
            _pattern(user_id=user_id, name="Thuê nhà",
                     expected_amount=Decimal("15000000")),
            _pattern(user_id=user_id, name="Internet",
                     category="utility",
                     expected_amount=Decimal("500000")),
            _pattern(user_id=user_id, name="Gym",
                     category="health",
                     expected_amount=Decimal("800000")),
        ]
        text = reminder_scheduler_job._format_bundled_reminder(patterns)
        assert "3 khoản" in text
        assert "Thuê nhà" in text
        assert "Internet" in text
        assert "Gym" in text
        assert "16,300,000" in text  # total


@pytest.mark.asyncio
class TestSendForUser:
    async def test_under_threshold_sends_individual(self):
        """2 patterns due same day → 2 single-pattern messages, not
        bundled."""
        user_id = uuid.uuid4()
        u = MagicMock(id=user_id, telegram_id=100, deleted_at=None)
        patterns = [
            _pattern(user_id=user_id, expected_day=5, name="Thuê nhà"),
            _pattern(user_id=user_id, expected_day=5, name="Internet",
                     expected_amount=Decimal("500000")),
        ]
        db = MagicMock()
        with patch.object(
            reminder_scheduler_job, "send_message", new=AsyncMock(),
        ) as send:
            await reminder_scheduler_job._send_for_user(
                db, u, patterns, today=date(2026, 4, 5),
            )
        assert send.call_count == 2
        # Each call uses the single-pattern keyboard (1 button →
        # ``reminder:paid:<uuid>``), not the bundle keyboard.
        for call in send.call_args_list:
            kb = call.kwargs["reply_markup"]
            buttons = [
                btn for row in kb["inline_keyboard"] for btn in row
            ]
            cb_data = " ".join(b["callback_data"] for b in buttons)
            assert "paid_all" not in cb_data

    async def test_threshold_3_bundles(self):
        """3 patterns due same day → ONE bundled message."""
        user_id = uuid.uuid4()
        u = MagicMock(id=user_id, telegram_id=100, deleted_at=None)
        patterns = [
            _pattern(user_id=user_id, expected_day=5, name=f"P{i}",
                     expected_amount=Decimal("100000"))
            for i in range(3)
        ]
        db = MagicMock()
        with patch.object(
            reminder_scheduler_job, "send_message", new=AsyncMock(),
        ) as send:
            await reminder_scheduler_job._send_for_user(
                db, u, patterns, today=date(2026, 4, 5),
            )
        assert send.call_count == 1
        # Bundle keyboard contains ``paid_all``.
        kb = send.call_args.kwargs["reply_markup"]
        buttons = [btn for row in kb["inline_keyboard"] for btn in row]
        cb_data = " ".join(b["callback_data"] for b in buttons)
        assert "paid_all" in cb_data
