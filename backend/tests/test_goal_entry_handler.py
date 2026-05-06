"""Tests for ``backend.bot.handlers.goal_entry``.

Telegram + DB are mocked; we focus on:
- Template pick advances to amount step + records template_id.
- Custom-name path collects a name first.
- Amount input parses VND + advances to date step.
- Date pick (preset / skip / custom) routes correctly.
- Save commits via ``goal_service.create_goal``.
- Edit-progress / edit-amount / edit-date sub-wizards.
- Delete 2-tap confirm.
- Cancel clears goal_* state but not other wizards.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import goal_entry
from backend.models.goal import Goal
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


def _saved_goal() -> Goal:
    g = Goal()
    g.id = uuid.uuid4()
    g.user_id = uuid.uuid4()
    g.name = "Mua xe"
    g.template_id = "buy_car"
    g.icon = "🚗"
    g.target_amount = Decimal("800000000")
    g.current_amount = Decimal("0")
    g.target_date = date(2028, 5, 1)
    g.status = "active"
    g.priority = 5
    g.monthly_savings_required = None
    return g


# ---------------------------------------------------------------------
# Add flow — template path
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestTemplatePick:
    async def test_buy_car_advances_to_amount(self):
        user = _user({"flow": goal_entry.FLOW_ADD, "step": "template", "draft": {}})
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(goal_entry, "answer_callback", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_callback(
                db,
                {"id": "cb1", "data": "goals:template:buy_car",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kw = advance.await_args.kwargs
        assert kw["step"] == "amount"
        # Template fields land on the draft.
        assert kw["draft_patch"]["template_id"] == "buy_car"
        assert kw["draft_patch"]["icon"] == "🚗"
        assert kw["draft_patch"]["name"] == "Mua xe"


@pytest.mark.asyncio
class TestCustomNamePath:
    async def test_custom_picks_name_input_step(self):
        user = _user({"flow": goal_entry.FLOW_ADD, "step": "template", "draft": {}})
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(goal_entry, "answer_callback", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_callback(
                db,
                {"id": "cb1", "data": "goals:custom",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        assert advance.await_args.kwargs["step"] == "custom_name"

    async def test_custom_name_input_advances_to_amount(self):
        user = _user({"flow": goal_entry.FLOW_ADD, "step": "custom_name",
                      "draft": {}})
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_text_input(
                db,
                {"text": "Mua máy ảnh", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kw = advance.await_args.kwargs
        assert kw["step"] == "amount"
        assert kw["draft_patch"]["name"] == "Mua máy ảnh"
        assert kw["draft_patch"]["template_id"] is None


# ---------------------------------------------------------------------
# Amount + date inputs
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestAmountInput:
    async def test_parses_vnd_and_advances_to_date(self):
        user = _user({"flow": goal_entry.FLOW_ADD, "step": "amount",
                      "draft": {"name": "Mua xe", "template_id": "buy_car"}})
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_text_input(
                db,
                {"text": "800tr", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kw = advance.await_args.kwargs
        assert kw["step"] == "date"
        assert kw["draft_patch"]["target_amount"] == 800_000_000

    async def test_negative_amount_rejected(self):
        user = _user({"flow": goal_entry.FLOW_ADD, "step": "amount",
                      "draft": {"name": "x"}})
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_text_input(
                db,
                {"text": "-10tr", "chat": {"id": 100}, "from": {"id": 100}},
            )
        advance.assert_not_awaited()


@pytest.mark.asyncio
class TestDatePick:
    async def test_skip_advances_to_preview_with_no_date(self):
        user = _user({
            "flow": goal_entry.FLOW_ADD, "step": "date",
            "draft": {
                "name": "Mua xe", "target_amount": 800_000_000,
                "template_id": "buy_car", "icon": "🚗",
            },
        })
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(goal_entry, "_show_preview", AsyncMock()), \
             patch.object(goal_entry, "answer_callback", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_callback(
                db,
                {"id": "cb1", "data": "goals:date:skip",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kw = advance.await_args.kwargs
        assert kw["step"] == "preview"
        assert kw["draft_patch"]["target_date_iso"] is None

    async def test_2y_preset_sets_iso_date(self):
        user = _user({
            "flow": goal_entry.FLOW_ADD, "step": "date",
            "draft": {"name": "x", "target_amount": 100, "template_id": None},
        })
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.wizard_service, "update_step",
                          AsyncMock()) as advance, \
             patch.object(goal_entry, "_show_preview", AsyncMock()), \
             patch.object(goal_entry, "answer_callback", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_callback(
                db,
                {"id": "cb1", "data": "goals:date:2y",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        advance.assert_awaited_once()
        kw = advance.await_args.kwargs
        # 2 years from today; check it's a valid future ISO date.
        iso = kw["draft_patch"]["target_date_iso"]
        parsed = date.fromisoformat(iso)
        assert parsed.year >= datetime.now().year + 1


# ---------------------------------------------------------------------
# Save flow
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestSave:
    async def test_save_creates_goal_via_service(self):
        user = _user({
            "flow": goal_entry.FLOW_ADD, "step": "preview",
            "draft": {
                "name": "Mua xe", "target_amount": 800_000_000,
                "target_date_iso": "2028-05-01",
                "template_id": "buy_car", "icon": "🚗",
            },
        })
        db = _db(user)
        saved = _saved_goal()
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry, "_refresh_user",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.goal_service, "create_goal",
                          AsyncMock(return_value=saved)) as create_mock, \
             patch.object(goal_entry.goal_projection, "get_avg_monthly_savings",
                          AsyncMock(return_value=Decimal(0))), \
             patch.object(goal_entry.wizard_service, "clear", AsyncMock()), \
             patch.object(goal_entry, "answer_callback", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_callback(
                db,
                {"id": "cb1", "data": "goals:save",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        create_mock.assert_awaited_once()
        payload = create_mock.await_args.args[2]
        assert payload.name == "Mua xe"
        assert payload.target_amount == Decimal("800000000")
        assert payload.target_date == date(2028, 5, 1)
        assert payload.template_id == "buy_car"


# ---------------------------------------------------------------------
# Edit-progress sub-wizard
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestEditProgress:
    async def test_progress_input_calls_update_progress(self):
        user = _user({
            "flow": goal_entry.FLOW_EDIT_PROGRESS, "step": "amount",
            "draft": {"goal_id": str(uuid.uuid4())},
        })
        db = _db(user)
        updated = _saved_goal()
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.goal_service, "update_goal_progress",
                          AsyncMock(return_value=updated)) as update_mock, \
             patch.object(goal_entry.goal_projection, "get_avg_monthly_savings",
                          AsyncMock(return_value=Decimal("10000000"))), \
             patch.object(goal_entry.wizard_service, "clear", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_text_input(
                db,
                {"text": "200tr", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        update_mock.assert_awaited_once()
        payload = update_mock.await_args.args[3]
        assert payload.current_amount == Decimal("200000000")


# ---------------------------------------------------------------------
# Delete 2-tap
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestDelete:
    async def test_delete_first_tap_shows_confirm_no_delete(self):
        user = _user()
        db = _db(user)
        gid = uuid.uuid4()
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.goal_service, "delete_goal",
                          AsyncMock()) as delete_mock, \
             patch.object(goal_entry, "answer_callback", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_callback(
                db,
                {"id": "cb1", "data": f"goals:delete:{gid}",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        delete_mock.assert_not_awaited()

    async def test_delete_confirm_actually_deletes(self):
        user = _user()
        db = _db(user)
        gid = uuid.uuid4()
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.goal_service, "delete_goal",
                          AsyncMock(return_value=True)) as delete_mock, \
             patch.object(goal_entry, "answer_callback", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()):
            await goal_entry.handle_goals_callback(
                db,
                {"id": "cb1", "data": f"goals:delete_confirm:{gid}",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        delete_mock.assert_awaited_once()


# ---------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestCancel:
    async def test_cancel_clears_goal_wizard(self):
        user = _user({"flow": goal_entry.FLOW_ADD, "step": "amount", "draft": {}})
        db = _db(user)
        with patch.object(goal_entry.wizard_service, "clear",
                          AsyncMock()) as clear, \
             patch.object(goal_entry, "send_message", AsyncMock()):
            consumed = await goal_entry.cancel_wizard(db, 100, user)
        assert consumed is True
        clear.assert_awaited_once()

    async def test_cancel_noop_for_non_goal_flow(self):
        user = _user({"flow": "asset_add_cash", "step": "amount", "draft": {}})
        db = _db(user)
        with patch.object(goal_entry.wizard_service, "clear",
                          AsyncMock()) as clear:
            consumed = await goal_entry.cancel_wizard(db, 100, user)
        assert consumed is False
        clear.assert_not_awaited()
