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
             patch.object(goal_entry, "_send_goals_submenu", AsyncMock()) as nav:
            consumed = await goal_entry.cancel_wizard(db, 100, user)
        assert consumed is True
        clear.assert_awaited_once()
        nav.assert_awaited_once_with(100, user)

    async def test_cancel_noop_for_non_goal_flow(self):
        user = _user({"flow": "asset_add_cash", "step": "amount", "draft": {}})
        db = _db(user)
        with patch.object(goal_entry.wizard_service, "clear",
                          AsyncMock()) as clear:
            consumed = await goal_entry.cancel_wizard(db, 100, user)
        assert consumed is False
        clear.assert_not_awaited()


# ---------------------------------------------------------------------
# Issue #450 §2 — edit-date auto-recalculates monthly savings
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestEditDateAutoRecalc:
    async def _run(self, goal: Goal, text: str = "2028-12-31"):
        gid = uuid.uuid4()
        goal.id = gid
        user = _user({
            "flow": goal_entry.FLOW_EDIT_DATE, "step": "date_input",
            "draft": {"goal_id": str(gid)},
        })
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.goal_service, "update_goal",
                          AsyncMock(return_value=goal)), \
             patch.object(goal_entry.goal_projection, "get_avg_monthly_savings",
                          AsyncMock(return_value=Decimal("10000000"))), \
             patch.object(goal_entry.wizard_service, "clear", AsyncMock()), \
             patch.object(goal_entry, "send_message", AsyncMock()) as send:
            await goal_entry.handle_goals_text_input(
                db,
                {"text": text, "chat": {"id": 100}, "from": {"id": 100}},
            )
        return goal, send

    async def test_recalculates_and_writes_to_cache(self):
        """After a target_date change the new monthly_savings_required
        must be written onto the Goal row so the list view picks it up."""
        goal = _saved_goal()
        goal.current_amount = Decimal("100000000")
        goal.target_amount = Decimal("800000000")

        goal, send = await self._run(goal)

        # Cache column populated with a positive number, not the
        # pre-edit value (which was None on _saved_goal).
        assert goal.monthly_savings_required is not None
        assert goal.monthly_savings_required > 0
        send.assert_awaited()
        msg = send.await_args.kwargs.get("text") or send.await_args.args[1]
        assert "Cần tiết kiệm" in msg

    async def test_already_met_shows_celebration_not_savings(self):
        """Edge case spec'd in issue: target_amount <= current_amount
        should NOT compute required savings — show celebration."""
        goal = _saved_goal()
        goal.current_amount = Decimal("800000000")
        goal.target_amount = Decimal("800000000")

        _, send = await self._run(goal)

        msg = send.await_args.kwargs.get("text") or send.await_args.args[1]
        assert "đã đạt" in msg.lower() or "🎉" in msg

    async def test_past_due_input_rejected(self):
        """target_date <= today must be rejected with the spec'd Vi
        message before any DB write."""
        gid = uuid.uuid4()
        user = _user({
            "flow": goal_entry.FLOW_EDIT_DATE, "step": "date_input",
            "draft": {"goal_id": str(gid)},
        })
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.goal_service, "update_goal",
                          AsyncMock()) as update_mock, \
             patch.object(goal_entry, "send_message", AsyncMock()) as send:
            # 2000-01-01 is firmly in the past — rejection is unambiguous.
            await goal_entry.handle_goals_text_input(
                db,
                {"text": "2000-01-01", "chat": {"id": 100},
                 "from": {"id": 100}},
            )
        update_mock.assert_not_called()
        msg = send.await_args.kwargs.get("text") or send.await_args.args[1]
        assert "sau hôm nay" in msg

    async def test_skip_clears_target_date(self):
        """``skip`` resets the goal to open-ended — issue allows this
        and the cancellation copy must reflect that."""
        goal = _saved_goal()
        goal.target_date = None

        _, send = await self._run(goal, text="skip")

        msg = send.await_args.kwargs.get("text") or send.await_args.args[1]
        assert "open-ended" in msg or "bỏ hạn" in msg.lower()


# ---------------------------------------------------------------------
# Issue #450 §4 — cancel navigates back to goals list (not dead-end)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestCancelNavigatesToList:
    async def test_cancel_callback_lands_on_goals_submenu(self):
        user = _user({
            "flow": goal_entry.FLOW_ADD, "step": "template", "draft": {},
        })
        db = _db(user)
        with patch.object(goal_entry, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(goal_entry.wizard_service, "clear",
                          AsyncMock()) as clear, \
             patch.object(goal_entry, "_send_goals_submenu",
                          AsyncMock()) as nav, \
             patch.object(goal_entry, "answer_callback", AsyncMock()):
            await goal_entry.handle_goals_callback(
                db,
                {"id": "cb1", "data": "goals:cancel",
                 "message": {"chat": {"id": 100}, "message_id": 1},
                 "from": {"id": 100}},
            )
        clear.assert_awaited_once()
        nav.assert_awaited_once()


# ---------------------------------------------------------------------
# Issue #450 §4 — keyboard labels updated
# ---------------------------------------------------------------------


def test_template_keyboard_uses_quay_ve_label():
    from backend.bot.keyboards.goals_keyboard import goals_template_keyboard

    rows = goals_template_keyboard()["inline_keyboard"]
    flat = [btn for row in rows for btn in row]
    cancel = next(b for b in flat if b["callback_data"].endswith(":cancel"))
    assert cancel["text"] == "◀️ Quay về"
    # No legacy destructive copy lingers.
    assert "Hủy" not in cancel["text"]


def test_date_keyboard_uses_quay_ve_label():
    from backend.bot.keyboards.goals_keyboard import goals_date_keyboard

    rows = goals_date_keyboard()["inline_keyboard"]
    flat = [btn for row in rows for btn in row]
    cancel = next(b for b in flat if b["callback_data"].endswith(":cancel"))
    assert cancel["text"] == "◀️ Quay về"


def test_save_keyboard_uses_quay_ve_label():
    from backend.bot.keyboards.goals_keyboard import goals_save_keyboard

    rows = goals_save_keyboard()["inline_keyboard"]
    flat = [btn for row in rows for btn in row]
    cancel = next(b for b in flat if b["callback_data"].endswith(":cancel"))
    assert cancel["text"] == "◀️ Quay về"


def test_goals_footer_can_return_to_cashflow_context():
    from backend.bot.keyboards.goals_keyboard import goals_list_footer_keyboard

    keyboard = goals_list_footer_keyboard(
        back_callback="menu:cashflow",
        back_label="◀️ Quay về Dòng tiền",
    )

    back = keyboard["inline_keyboard"][-1][0]
    assert back["callback_data"] == "menu:cashflow"
    assert back["text"] == "◀️ Quay về Dòng tiền"
