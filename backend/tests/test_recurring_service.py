"""Unit tests for ``backend.services.recurring_service``.

DB-free with a fake AsyncSession (mirrors test_rental_service /
test_income_stream_service). We assert:

- CRUD: add / update / disable / disable_reminders / snooze.
- ``get_next_expected_date`` schedule arithmetic — including
  month-end clamping (Feb 31 → Feb 28/29) and "already paid this
  month → next month".
- ``record_occurrence`` creates an Expense with ``is_recurring=True``
  + ``recurrence_id`` pointing at the pattern.
- ``was_paid_this_period`` returns True/False correctly.
- Boundary contract: service flushes; never commits.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.expense import Expense
from backend.models.recurring_pattern import RecurringPattern
from backend.services import recurring_service


def _make_pattern(
    *,
    user_id: uuid.UUID,
    name: str = "Thuê nhà",
    category: str = "housing",
    expected_amount: Decimal = Decimal("15000000"),
    expected_day: int | None = 5,
    enable_reminders: bool = True,
    is_active: bool = True,
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
    p.auto_detected = False
    p.user_confirmed = True
    p.enable_reminders = enable_reminders
    p.reminder_days_before = 2
    p.last_reminder_sent = None
    p.snooze_until = None
    p.last_occurrence_date = last_occurrence_date
    p.occurrence_count = 0
    p.created_at = datetime.utcnow()
    p.updated_at = datetime.utcnow()
    return p


def _result_with_scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    scalars = MagicMock()
    scalars.all.return_value = [value] if value is not None else []
    result.scalars.return_value = scalars
    return result


def _mock_session(execute_side_effect=None) -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock()
    if execute_side_effect is not None:
        db.execute.side_effect = execute_side_effect
    return db


def _assert_flush_only(db: MagicMock) -> None:
    db.flush.assert_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestAddPattern:
    async def test_creates_pattern_with_defaults(self):
        user_id = uuid.uuid4()
        db = _mock_session()
        p = await recurring_service.add_pattern(
            db, user_id,
            name="Internet", category="utility",
            expected_amount=Decimal("500000"),
            expected_day_of_month=1,
        )
        assert p.user_id == user_id
        assert p.name == "Internet"
        assert p.category == "utility"
        assert p.expected_amount == Decimal("500000")
        assert p.expected_day_of_month == 1
        assert p.schedule_type == "monthly"
        assert p.enable_reminders is True
        assert p.is_active is True
        added = [c.args[0] for c in db.add.call_args_list]
        assert any(isinstance(x, RecurringPattern) for x in added)
        _assert_flush_only(db)

    async def test_negative_amount_rejected(self):
        db = _mock_session()
        with pytest.raises(ValueError, match="positive"):
            await recurring_service.add_pattern(
                db, uuid.uuid4(),
                name="x", category="other",
                expected_amount=Decimal("-1"),
            )

    async def test_invalid_day_rejected(self):
        db = _mock_session()
        with pytest.raises(ValueError, match="1-31"):
            await recurring_service.add_pattern(
                db, uuid.uuid4(),
                name="x", category="other",
                expected_amount=Decimal("100"),
                expected_day_of_month=32,
            )


@pytest.mark.asyncio
class TestUpdatePattern:
    async def test_partial_update(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id)
        db = _mock_session([_result_with_scalar(pattern)])
        await recurring_service.update_pattern(
            db, user_id, pattern.id,
            expected_amount=Decimal("16000000"),
        )
        assert pattern.expected_amount == Decimal("16000000")
        # Other fields untouched.
        assert pattern.name == "Thuê nhà"

    async def test_unknown_field_raises(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id)
        db = _mock_session([_result_with_scalar(pattern)])
        with pytest.raises(ValueError, match="Unknown field"):
            await recurring_service.update_pattern(
                db, user_id, pattern.id, nonexistent="x",
            )

    async def test_missing_pattern_raises(self):
        db = _mock_session([_result_with_scalar(None)])
        with pytest.raises(ValueError, match="not found"):
            await recurring_service.update_pattern(
                db, uuid.uuid4(), uuid.uuid4(),
                expected_amount=Decimal("1"),
            )


@pytest.mark.asyncio
class TestDisableAndSnooze:
    async def test_disable_pattern_sets_inactive(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id, is_active=True)
        db = _mock_session([_result_with_scalar(pattern)])
        await recurring_service.disable_pattern(db, user_id, pattern.id)
        assert pattern.is_active is False

    async def test_disable_reminders_keeps_pattern_active(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(
            user_id=user_id, is_active=True, enable_reminders=True,
        )
        db = _mock_session([_result_with_scalar(pattern)])
        await recurring_service.disable_reminders(
            db, user_id, pattern.id,
        )
        assert pattern.enable_reminders is False
        # Pattern itself stays alive — user wants to remember it
        # without being pinged.
        assert pattern.is_active is True

    async def test_snooze_sets_future_date(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id)
        db = _mock_session([_result_with_scalar(pattern)])
        await recurring_service.snooze_pattern(
            db, user_id, pattern.id, days=2,
        )
        assert pattern.snooze_until is not None
        assert pattern.snooze_until > date.today()

    async def test_snooze_zero_days_rejected(self):
        db = _mock_session([_result_with_scalar(_make_pattern(user_id=uuid.uuid4()))])
        with pytest.raises(ValueError, match="positive"):
            await recurring_service.snooze_pattern(
                db, uuid.uuid4(), uuid.uuid4(), days=0,
            )


class TestNextExpectedDate:
    """Pure function — exercise edge cases without DB."""

    def test_basic_monthly_before_due_day(self):
        """Today=Apr 1, day=5 → Apr 5."""
        pattern = _make_pattern(user_id=uuid.uuid4(), expected_day=5)
        result = recurring_service.get_next_expected_date(
            pattern, today=date(2026, 4, 1),
        )
        assert result == date(2026, 4, 5)

    def test_basic_monthly_after_due_day(self):
        """Today=Apr 10, day=5 → May 5."""
        pattern = _make_pattern(user_id=uuid.uuid4(), expected_day=5)
        result = recurring_service.get_next_expected_date(
            pattern, today=date(2026, 4, 10),
        )
        assert result == date(2026, 5, 5)

    def test_already_paid_this_month_jumps_to_next(self):
        """If last_occurrence_date is in the current month, next due is
        next month — we don't ping again for the same period."""
        pattern = _make_pattern(
            user_id=uuid.uuid4(), expected_day=5,
            last_occurrence_date=date(2026, 4, 5),
        )
        result = recurring_service.get_next_expected_date(
            pattern, today=date(2026, 4, 10),
        )
        assert result == date(2026, 5, 5)

    def test_month_end_clamping_february(self):
        """Day=31, today=Feb 1 → Feb 28 (or Feb 29 in leap years).
        Must never throw — Feb 31 isn't a valid date."""
        pattern = _make_pattern(user_id=uuid.uuid4(), expected_day=31)
        result = recurring_service.get_next_expected_date(
            pattern, today=date(2026, 2, 1),
        )
        # 2026 is not a leap year.
        assert result == date(2026, 2, 28)

    def test_month_wrap_december_to_january(self):
        """Today=Dec 15, day=5 → Jan 5 next year."""
        pattern = _make_pattern(user_id=uuid.uuid4(), expected_day=5)
        result = recurring_service.get_next_expected_date(
            pattern, today=date(2026, 12, 15),
        )
        assert result == date(2027, 1, 5)

    def test_no_expected_day_falls_back_to_30_day_default(self):
        last = date(2026, 4, 1)
        pattern = _make_pattern(
            user_id=uuid.uuid4(), expected_day=None,
            last_occurrence_date=last,
        )
        result = recurring_service.get_next_expected_date(
            pattern, today=date(2026, 4, 10),
        )
        assert (result - last).days == 30


@pytest.mark.asyncio
class TestRecordOccurrence:
    async def test_default_amount_uses_expected(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id)
        db = _mock_session([_result_with_scalar(pattern)])
        expense = await recurring_service.record_occurrence(
            db, user_id, pattern.id,
        )
        assert expense.amount == pattern.expected_amount
        assert expense.is_recurring is True
        assert expense.recurrence_id == pattern.id
        assert expense.merchant == pattern.name
        assert expense.category == pattern.category
        # Pattern tracking bumped.
        assert pattern.last_occurrence_date == date.today()
        assert pattern.occurrence_count == 1

    async def test_explicit_amount_used(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id)
        db = _mock_session([_result_with_scalar(pattern)])
        expense = await recurring_service.record_occurrence(
            db, user_id, pattern.id, amount=Decimal("16000000"),
        )
        assert expense.amount == Decimal("16000000")

    async def test_zero_amount_rejected(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id)
        db = _mock_session([_result_with_scalar(pattern)])
        with pytest.raises(ValueError, match="positive"):
            await recurring_service.record_occurrence(
                db, user_id, pattern.id, amount=Decimal("0"),
            )


@pytest.mark.asyncio
class TestWasPaidThisPeriod:
    async def test_returns_true_when_expense_in_period(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id)
        # Mock the `Expense.id` lookup to return a row.
        db = _mock_session([_result_with_scalar(uuid.uuid4())])
        result = await recurring_service.was_paid_this_period(
            db, pattern, today=date(2026, 4, 10),
        )
        assert result is True

    async def test_returns_false_when_no_expense(self):
        user_id = uuid.uuid4()
        pattern = _make_pattern(user_id=user_id)
        db = _mock_session([_result_with_scalar(None)])
        result = await recurring_service.was_paid_this_period(
            db, pattern, today=date(2026, 4, 10),
        )
        assert result is False
