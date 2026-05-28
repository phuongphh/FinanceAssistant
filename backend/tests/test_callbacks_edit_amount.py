"""Issue #897 — 💵 button prompts via force_reply + wizard captures text."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.bot.handlers import callbacks, message as message_handler


@pytest.mark.asyncio
async def test_edit_amount_starts_wizard_and_sends_force_reply(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    start_flow = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "start_flow", start_flow)
    send = AsyncMock()
    monkeypatch.setattr(callbacks, "send_message", send)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    await callbacks._handle_edit_amount(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=["tx-1"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    start_flow.assert_awaited_once()
    kwargs = start_flow.await_args.kwargs
    assert kwargs["flow"] == "transaction_amount_edit"
    assert kwargs["draft"]["expense_id"] == "tx-1"
    send.assert_awaited_once()
    send_kwargs = send.await_args.kwargs
    assert send_kwargs["reply_markup"] == {"force_reply": True, "selective": True}


@pytest.mark.asyncio
async def test_amount_edit_text_reply_applies_update(monkeypatch):
    user = SimpleNamespace(
        id=42,
        wizard_state={
            "flow": "transaction_amount_edit",
            "step": "await_amount",
            "draft": {"expense_id": "tx-1", "chat_id": 10, "message_id": 20},
        },
    )
    updated = SimpleNamespace(id="tx-1", transaction_type="expense")
    update_expense = AsyncMock(return_value=updated)
    monkeypatch.setattr(
        message_handler.expense_service, "update_expense", update_expense
    )
    clear = AsyncMock()
    monkeypatch.setattr(message_handler.wizard_service, "clear", clear)
    monkeypatch.setattr(message_handler, "send_message", AsyncMock())
    rerender = AsyncMock()
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", rerender)

    handled = await message_handler._maybe_handle_amount_edit(
        SimpleNamespace(), user, chat_id=10, text="60k"
    )
    assert handled is True
    update_expense.assert_awaited_once()
    update_arg = update_expense.await_args.args[3]
    assert float(update_arg.amount) == 60000.0
    clear.assert_awaited_once()
    rerender.assert_awaited_once()
    assert rerender.await_args.kwargs["edited"] is True


@pytest.mark.asyncio
async def test_amount_edit_invalid_text_asks_retry(monkeypatch):
    user = SimpleNamespace(
        id=42,
        wizard_state={
            "flow": "transaction_amount_edit",
            "draft": {"expense_id": "tx-1", "chat_id": 10, "message_id": 20},
        },
    )
    update_expense = AsyncMock()
    monkeypatch.setattr(
        message_handler.expense_service, "update_expense", update_expense
    )
    monkeypatch.setattr(message_handler.wizard_service, "clear", AsyncMock())
    send = AsyncMock()
    monkeypatch.setattr(message_handler, "send_message", send)

    handled = await message_handler._maybe_handle_amount_edit(
        SimpleNamespace(), user, chat_id=10, text="không phải số"
    )
    assert handled is True
    update_expense.assert_not_awaited()
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_amount_edit_not_in_flow_returns_false():
    user = SimpleNamespace(id=42, wizard_state={"flow": "something_else"})
    handled = await message_handler._maybe_handle_amount_edit(
        SimpleNamespace(), user, chat_id=10, text="60k"
    )
    assert handled is False
