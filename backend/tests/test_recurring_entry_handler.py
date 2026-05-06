"""Tests for ``backend.bot.handlers.recurring_entry``.

Covers the wizard add-flow (name → amount → category → schedule_day
→ reminders) and the reminder action callbacks (paid / delay /
disable). Telegram + DB are mocked; we focus on dispatch correctness
and side effects on the service.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import recurring_entry
from backend.models.recurring_pattern import RecurringPattern
from backend.models.user import User


def _user(state: dict | None = None) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 100
    u.display_name = "Test"
    u.wizard_state = state
    u.created_at = datetime.utcnow()
    return u


def _db(user: User | None = None) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    return db


def _pattern() -> RecurringPattern:
    p = RecurringPattern()
    p.id = uuid.uuid4()
    p.user_id = uuid.uuid4()
    p.name = "Thuê nhà"
    p.category = "housing"
    p.expected_amount = Decimal("15000000")
    p.amount_variance_pct = 10.0
    p.schedule_type = "monthly"
    p.expected_day_of_month = 5
    p.is_active = True
    p.enable_reminders = True
    p.reminder_days_before = 2
    p.last_reminder_sent = None
    p.last_occurrence_date = None
    p.occurrence_count = 0
    return p


# ---------------------------------------------------------------------
# Add wizard flow
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestAddFlow:
    async def test_name_input_advances_to_amount(self):
        user = _user({
            "flow": recurring_entry.FLOW_ADD, "step": "name", "draft": {},
        })
        db = _db(user)
        with patch.object(recurring_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(recurring_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            await recurring_entry.handle_recurring_text_input(
                db,
                {"text": "Thuê nhà", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kw = advance.await_args.kwargs
        assert kw["step"] == "amount"
        assert kw["draft_patch"]["name"] == "Thuê nhà"

    async def test_amount_input_advances_to_category(self):
        user = _user({
            "flow": recurring_entry.FLOW_ADD, "step": "amount",
            "draft": {"name": "Thuê nhà"},
        })
        db = _db(user)
        with patch.object(recurring_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(recurring_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            await recurring_entry.handle_recurring_text_input(
                db,
                {"text": "15tr", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kw = advance.await_args.kwargs
        assert kw["step"] == "category"
        assert kw["draft_patch"]["amount"] == 15_000_000

    async def test_negative_amount_rejected_no_advance(self):
        user = _user({
            "flow": recurring_entry.FLOW_ADD, "step": "amount",
            "draft": {"name": "x"},
        })
        db = _db(user)
        with patch.object(recurring_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(recurring_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            await recurring_entry.handle_recurring_text_input(
                db,
                {"text": "-15tr", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_not_awaited()

    async def test_schedule_day_zero_means_no_fixed_day(self):
        user = _user({
            "flow": recurring_entry.FLOW_ADD, "step": "schedule_day",
            "draft": {"name": "x", "amount": 100, "category": "other"},
        })
        db = _db(user)
        with patch.object(recurring_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(recurring_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            await recurring_entry.handle_recurring_text_input(
                db,
                {"text": "0", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kw = advance.await_args.kwargs
        assert kw["draft_patch"]["schedule_day"] is None

    async def test_reminders_pick_creates_pattern(self):
        user = _user({
            "flow": recurring_entry.FLOW_ADD, "step": "reminders",
            "draft": {
                "name": "Thuê nhà", "amount": 15_000_000,
                "category": "housing", "schedule_day": 5,
            },
        })
        db = _db(user)
        created = _pattern()
        with patch.object(recurring_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(recurring_entry.recurring_service, "add_pattern",
                          AsyncMock(return_value=created)) as add_mock, \
             patch.object(recurring_entry.wizard_service, "clear", AsyncMock()), \
             patch.object(recurring_entry, "answer_callback", AsyncMock()), \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            await recurring_entry.handle_recurring_callback(
                db,
                {"id": "cb1", "data": "recurring:reminders:on",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        add_mock.assert_awaited_once()
        kwargs = add_mock.await_args.kwargs
        assert kwargs["name"] == "Thuê nhà"
        assert kwargs["category"] == "housing"
        assert kwargs["expected_day_of_month"] == 5
        assert kwargs["enable_reminders"] is True


# ---------------------------------------------------------------------
# Reminder action handlers (S10)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestReminderActions:
    async def test_paid_records_occurrence(self):
        user = _user()
        db = _db(user)
        pattern = _pattern()
        expense = MagicMock()
        expense.amount = Decimal("15000000")
        with patch.object(recurring_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(recurring_entry.recurring_service, "get_pattern_by_id",
                          AsyncMock(return_value=pattern)), \
             patch.object(recurring_entry.recurring_service, "record_occurrence",
                          AsyncMock(return_value=expense)) as record_mock, \
             patch.object(recurring_entry.recurring_service, "get_next_expected_date",
                          MagicMock(return_value=date(2026, 5, 5))), \
             patch.object(recurring_entry, "answer_callback", AsyncMock()), \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            await recurring_entry.handle_recurring_callback(
                db,
                {"id": "cb1", "data": f"reminder:paid:{pattern.id}",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        record_mock.assert_awaited_once()

    async def test_delay_snoozes_2_days(self):
        user = _user()
        db = _db(user)
        pid = uuid.uuid4()
        with patch.object(recurring_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(recurring_entry.recurring_service, "snooze_pattern",
                          AsyncMock()) as snooze, \
             patch.object(recurring_entry, "answer_callback", AsyncMock()), \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            await recurring_entry.handle_recurring_callback(
                db,
                {"id": "cb1", "data": f"reminder:delay:{pid}",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        snooze.assert_awaited_once()
        # Default snooze duration is 2 days per spec.
        assert snooze.await_args.kwargs.get("days") == 2

    async def test_disable_calls_disable_reminders(self):
        user = _user()
        db = _db(user)
        pid = uuid.uuid4()
        with patch.object(recurring_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(recurring_entry.recurring_service, "disable_reminders",
                          AsyncMock()) as disable, \
             patch.object(recurring_entry, "answer_callback", AsyncMock()), \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            await recurring_entry.handle_recurring_callback(
                db,
                {"id": "cb1", "data": f"reminder:disable:{pid}",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        disable.assert_awaited_once()


# ---------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestCancel:
    async def test_cancel_clears_recurring_wizard(self):
        user = _user({
            "flow": recurring_entry.FLOW_ADD, "step": "amount", "draft": {},
        })
        db = _db(user)
        with patch.object(recurring_entry.wizard_service, "clear",
                          AsyncMock()) as clear, \
             patch.object(recurring_entry, "send_message", AsyncMock()):
            consumed = await recurring_entry.cancel_wizard(db, 100, user)
        assert consumed is True
        clear.assert_awaited_once()

    async def test_cancel_noop_for_non_recurring_flow(self):
        user = _user({"flow": "asset_add_cash", "step": "amount", "draft": {}})
        db = _db(user)
        with patch.object(recurring_entry.wizard_service, "clear",
                          AsyncMock()) as clear:
            consumed = await recurring_entry.cancel_wizard(db, 100, user)
        assert consumed is False
        clear.assert_not_awaited()
