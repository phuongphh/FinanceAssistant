"""Issue #897 — 2-step source edit via inline keyboard."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.bot.handlers import callbacks


@pytest.mark.asyncio
async def test_change_source_one_arg_swaps_to_picker_and_starts_wizard(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")

    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    start_flow = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "start_flow", start_flow)
    edit_markup = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    answer = AsyncMock()
    monkeypatch.setattr(callbacks, "answer_callback", answer)

    db = SimpleNamespace()
    user = SimpleNamespace(id=42)

    await callbacks._handle_change_source(
        db=db,
        user=user,
        args=["tx-1"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    start_flow.assert_awaited_once()
    kwargs = start_flow.await_args.kwargs
    assert kwargs["flow"] == "transaction_source_edit"
    assert kwargs["step"] == "pick_kind"
    assert kwargs["draft"]["expense_id"] == "tx-1"
    edit_markup.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_source_cash_applies_immediately(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    updated = SimpleNamespace(id="tx-1", transaction_type="expense")

    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    update_expense = AsyncMock(return_value=updated)
    monkeypatch.setattr(callbacks.expense_service, "update_expense", update_expense)
    clear = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "clear", clear)
    rerender = AsyncMock()
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", rerender)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    db = SimpleNamespace()
    user = SimpleNamespace(id=42)

    await callbacks._handle_change_source(
        db=db,
        user=user,
        args=["tx-1", "cash"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    update_expense.assert_awaited_once()
    update_arg = update_expense.await_args.args[3]
    assert update_arg.source_type == "cash"
    clear.assert_awaited_once()
    rerender.assert_awaited_once_with(10, 20, updated, edited=True, db=db)


@pytest.mark.asyncio
async def test_change_source_wallet_swaps_to_subpicker(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    edit_markup = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    await callbacks._handle_change_source(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=["tx-1", "wallet"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )
    edit_markup.assert_awaited_once()
    markup = edit_markup.await_args.kwargs["reply_markup"]
    callbacks_data = [
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
    ]
    assert any(cd.startswith("chsrc_wl:momo") for cd in callbacks_data)


@pytest.mark.asyncio
async def test_change_source_subpicker_applies_bank(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    updated = SimpleNamespace(id="tx-1", transaction_type="expense")

    user = SimpleNamespace(
        id=42,
        wizard_state={
            "flow": "transaction_source_edit",
            "step": "pick_kind",
            "draft": {"expense_id": "tx-1", "chat_id": 10, "message_id": 20},
        },
    )

    monkeypatch.setattr(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    update_expense = AsyncMock(return_value=updated)
    monkeypatch.setattr(callbacks.expense_service, "update_expense", update_expense)
    clear = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "clear", clear)
    rerender = AsyncMock()
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", rerender)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    callback_query = {
        "id": "cb1",
        "data": "chsrc_bk:11111111-1111-1111-1111-111111111111",
        "from": {"id": 7},
        "message": {"chat": {"id": 10}, "message_id": 20},
    }
    handled = await callbacks._handle_change_source_subpicker(
        SimpleNamespace(), callback_query
    )
    assert handled is True
    update_arg = update_expense.await_args.args[3]
    assert update_arg.source_type == "bank_account"
    assert str(update_arg.source_asset_id) == "11111111-1111-1111-1111-111111111111"
    clear.assert_awaited_once()
    rerender.assert_awaited_once()
    assert rerender.await_args.args[:3] == (10, 20, updated)
    assert rerender.await_args.kwargs["edited"] is True


@pytest.mark.asyncio
async def test_change_source_subpicker_rejects_when_not_in_flow(monkeypatch):
    user = SimpleNamespace(id=42, wizard_state={"flow": "something_else"})
    monkeypatch.setattr(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    )
    answer = AsyncMock()
    monkeypatch.setattr(callbacks, "answer_callback", answer)

    callback_query = {
        "id": "cb1",
        "data": "chsrc_wl:momo",
        "from": {"id": 7},
        "message": {"chat": {"id": 10}, "message_id": 20},
    }
    handled = await callbacks._handle_change_source_subpicker(
        SimpleNamespace(), callback_query
    )
    assert handled is True
    answer.assert_awaited_once()
    assert answer.await_args.kwargs.get("show_alert") is True
