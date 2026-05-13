"""End-to-end-ish tests for the income-stream wizard handler.

Telegram + DB are mocked; we focus on:
- Type pick → amount step.
- Amount parsing ("Lương 30tr" → name + Decimal("30000000")).
- Schedule pick routes correctly:
  - monthly → schedule_day step
  - annually → schedule_month step
  - quarterly / ad_hoc → start_date directly
- Final commit calls income_service with validated payload.
- List view renders empty state vs populated state.
- Pause / resume / delete callbacks dispatch through the right
  service methods.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import income_entry
from backend.models.user import User
from backend.wealth.models.income_stream import IncomeStream


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


def _stream(stream_type: str = "salary", amount: Decimal = Decimal("30000000"),
            schedule: str = "monthly", *, is_passive: bool = False,
            is_active: bool = True, name: str = "Lương") -> IncomeStream:
    s = IncomeStream()
    s.id = uuid.uuid4()
    s.user_id = uuid.uuid4()
    s.stream_type = stream_type
    s.is_passive = is_passive
    s.name = name
    s.amount = amount
    s.currency = "VND"
    s.schedule_type = schedule
    s.start_date = date.today()
    s.is_active = is_active
    s.schedule_day = None
    s.schedule_month = None
    return s


# -----------------------------------------------------------------
# Add flow
# -----------------------------------------------------------------


@pytest.mark.asyncio
class TestTypePick:
    async def test_advances_to_amount_step(self):
        user = _user({"flow": income_entry.FLOW_ADD, "step": "type", "draft": {}})
        db = _db(user)
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(income_entry, "answer_callback", AsyncMock()), \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_callback(
                db,
                {"id": "cb1", "data": "income:type:salary",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kwargs = advance.await_args.kwargs
        assert kwargs["step"] == "amount"
        assert kwargs["draft_patch"]["stream_type"] == "salary"
        assert kwargs["draft_patch"]["is_passive"] is False
        assert kwargs["draft_patch"]["typical_schedule"] == "monthly"


@pytest.mark.asyncio
class TestAmountInput:
    async def test_parses_name_and_amount(self):
        user = _user({
            "flow": income_entry.FLOW_ADD, "step": "amount",
            "draft": {"stream_type": "salary"},
        })
        db = _db(user)
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_text_input(
                db,
                {"text": "Lương Tech 30tr", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        patch_kwargs = advance.await_args.kwargs
        assert patch_kwargs["step"] == "schedule"
        assert patch_kwargs["draft_patch"]["name"] == "Lương Tech"
        assert patch_kwargs["draft_patch"]["amount"] == 30_000_000

    async def test_negative_amount_rejected_no_advance(self):
        user = _user({
            "flow": income_entry.FLOW_ADD, "step": "amount",
            "draft": {"stream_type": "salary"},
        })
        db = _db(user)
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_text_input(
                db,
                {"text": "-30tr", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_not_awaited()

    async def test_unparseable_input_reprompts(self):
        user = _user({
            "flow": income_entry.FLOW_ADD, "step": "amount",
            "draft": {"stream_type": "salary"},
        })
        db = _db(user)
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(income_entry, "send_message", AsyncMock()):
            # No digits → can't extract amount.
            await income_entry.handle_income_text_input(
                db,
                {"text": "Lương Tech", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_not_awaited()


@pytest.mark.asyncio
class TestSchedulePick:
    async def test_monthly_routes_to_schedule_day(self):
        user = _user({
            "flow": income_entry.FLOW_ADD, "step": "schedule",
            "draft": {"stream_type": "salary", "name": "Lương",
                      "amount": 30_000_000},
        })
        db = _db(user)
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(income_entry, "answer_callback", AsyncMock()), \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_callback(
                db,
                {"id": "cb1", "data": "income:schedule:monthly",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        assert advance.await_args.kwargs["step"] == "schedule_day"

    async def test_annually_routes_to_schedule_month(self):
        user = _user({
            "flow": income_entry.FLOW_ADD, "step": "schedule",
            "draft": {"stream_type": "dividend"},
        })
        db = _db(user)
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(income_entry, "answer_callback", AsyncMock()), \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_callback(
                db,
                {"id": "cb1", "data": "income:schedule:annually",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        assert advance.await_args.kwargs["step"] == "schedule_month"

    async def test_ad_hoc_skips_to_start_date(self):
        user = _user({
            "flow": income_entry.FLOW_ADD, "step": "schedule",
            "draft": {"stream_type": "freelance"},
        })
        db = _db(user)
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(income_entry, "answer_callback", AsyncMock()), \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_callback(
                db,
                {"id": "cb1", "data": "income:schedule:ad_hoc",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        assert advance.await_args.kwargs["step"] == "start_date"


@pytest.mark.asyncio
class TestCommit:
    async def test_today_choice_creates_stream(self):
        user = _user({
            "flow": income_entry.FLOW_ADD, "step": "start_date",
            "draft": {
                "stream_type": "salary", "name": "Lương Tech",
                "amount": 30_000_000, "schedule_type": "monthly",
                "schedule_day": 5, "is_passive": False,
            },
        })
        db = _db(user)
        created = _stream()
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.income_service, "create_income_stream",
                          AsyncMock(return_value=created)) as create_mock, \
             patch.object(income_entry.wizard_service, "clear", AsyncMock()), \
             patch.object(income_entry, "answer_callback", AsyncMock()), \
             patch.object(income_entry, "send_message", AsyncMock()):
            with patch(
                "backend.wealth.services.threshold_service.update_user_thresholds",
                new=AsyncMock(),
            ):
                await income_entry.handle_income_callback(
                    db,
                    {"id": "cb1", "data": "income:start_date:today",
                     "message": {"chat": {"id": 100}, "message_id": 1},
                     "from": {"id": 100}},
                )
        create_mock.assert_awaited_once()
        # The validated payload made it through Pydantic.
        payload = create_mock.await_args.args[2]
        assert payload.name == "Lương Tech"
        assert payload.amount == Decimal("30000000")
        assert payload.schedule_type == "monthly"


# -----------------------------------------------------------------
# List view + Pause / Resume / Delete callbacks
# -----------------------------------------------------------------


@pytest.mark.asyncio
class TestListAndActions:
    async def test_empty_state_renders_friendly_message(self):
        user = _user()
        db = _db(user)
        with patch.object(income_entry.income_service, "get_active_streams",
                          AsyncMock(return_value=[])), \
             patch.object(income_entry, "send_message", AsyncMock()) as send:
            await income_entry.show_income_list(db, 100, user)
        send.assert_called()
        text = send.call_args.kwargs["text"]
        assert "Chưa có nguồn thu" in text

    async def test_pause_callback_invokes_service(self):
        user = _user()
        db = _db(user)
        sid = uuid.uuid4()
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.income_service, "pause_stream",
                          AsyncMock()) as pause, \
             patch.object(income_entry, "answer_callback", AsyncMock()), \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_callback(
                db,
                {"id": "cb1", "data": f"income:pause:{sid}",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        pause.assert_awaited_once()

    async def test_delete_requires_confirm(self):
        """First tap shows confirm — does NOT call delete_stream yet."""
        user = _user()
        db = _db(user)
        sid = uuid.uuid4()
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.income_service, "delete_stream",
                          AsyncMock()) as delete, \
             patch.object(income_entry, "answer_callback", AsyncMock()), \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_callback(
                db,
                {"id": "cb1", "data": f"income:delete:{sid}",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        delete.assert_not_awaited()

    async def test_delete_confirm_actually_deletes(self):
        user = _user()
        db = _db(user)
        sid = uuid.uuid4()
        with patch.object(income_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(income_entry.income_service, "delete_stream",
                          AsyncMock(return_value=True)) as delete, \
             patch.object(income_entry, "answer_callback", AsyncMock()), \
             patch.object(income_entry, "send_message", AsyncMock()):
            await income_entry.handle_income_callback(
                db,
                {"id": "cb1", "data": f"income:delete_confirm:{sid}",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        delete.assert_awaited_once()


# -----------------------------------------------------------------
# Cancel / cross-wizard guard
# -----------------------------------------------------------------


@pytest.mark.asyncio
class TestCancel:
    async def test_cancel_clears_income_wizard(self):
        user = _user({"flow": income_entry.FLOW_ADD, "step": "amount", "draft": {}})
        db = _db(user)
        with patch.object(income_entry.wizard_service, "clear",
                          AsyncMock()) as clear, \
             patch.object(income_entry, "send_message", AsyncMock()):
            consumed = await income_entry.cancel_wizard(db, 100, user)
        assert consumed is True
        clear.assert_awaited_once()

    async def test_cancel_noop_when_not_in_income_flow(self):
        """cancel_wizard only fires for ``income_*`` flows. An asset
        wizard or no-state user should be left alone (asset's own
        cancel_wizard handles those)."""
        user = _user({"flow": "asset_add_cash", "step": "amount", "draft": {}})
        db = _db(user)
        with patch.object(income_entry.wizard_service, "clear",
                          AsyncMock()) as clear:
            consumed = await income_entry.cancel_wizard(db, 100, user)
        assert consumed is False
        clear.assert_not_awaited()
