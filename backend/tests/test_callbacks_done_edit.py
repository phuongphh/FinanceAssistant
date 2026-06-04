"""Issue #897 — ✅ Đồng ý strips the inline keyboard and collapses the hint."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.bot.handlers import callbacks


def _make_expense(**overrides):
    defaults = dict(
        id="exp-1",
        amount=2_000_000,
        merchant="ăn tối",
        note=None,
        category="food",
        transaction_type="expense",
        created_at=datetime(2026, 6, 2, 5, 5),
        expense_date=None,
        raw_data=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_done_edit_rerenders_with_short_hint_and_empty_keyboard(monkeypatch):
    edit_text = AsyncMock()
    edit_markup = AsyncMock()
    answer = AsyncMock()
    resolve_tx = AsyncMock(return_value=_make_expense())
    resolve_source = AsyncMock(return_value="Tài khoản thanh toán [Techcombank]")

    monkeypatch.setattr(callbacks, "edit_message_text", edit_text)
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    monkeypatch.setattr(callbacks, "answer_callback", answer)
    monkeypatch.setattr(callbacks, "resolve_transaction_by_callback_id", resolve_tx)
    monkeypatch.setattr(
        callbacks, "resolve_source_label_for_expense", resolve_source
    )

    await callbacks._handle_done_edit(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=["exp-1"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    edit_text.assert_awaited_once()
    kwargs = edit_text.await_args.kwargs
    assert kwargs["chat_id"] == 10
    assert kwargs["message_id"] == 20
    assert kwargs["parse_mode"] == "HTML"
    assert kwargs["reply_markup"] == {"inline_keyboard": []}
    # Short hint replaces the long edit prompt
    assert "Chi tiêu đã được ghi lại" in kwargs["text"]
    assert "click vào các nhãn" not in kwargs["text"]
    # Merchant/amount/source still rendered
    assert "ăn tối" in kwargs["text"]
    assert "2,000,000đ" in kwargs["text"]
    assert "Techcombank" in kwargs["text"]

    edit_markup.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_done_edit_money_in_uses_money_in_hint(monkeypatch):
    edit_text = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_text", edit_text)
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", AsyncMock())
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=_make_expense(transaction_type="money_in")),
    )
    monkeypatch.setattr(
        callbacks,
        "resolve_source_label_for_expense",
        AsyncMock(return_value="Tiền mặt"),
    )

    await callbacks._handle_done_edit(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=["exp-1"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    text = edit_text.await_args.kwargs["text"]
    assert "Khoản tiền vào đã được ghi lại" in text
    assert "Chi tiêu đã được ghi lại" not in text


@pytest.mark.asyncio
async def test_done_edit_falls_back_to_strip_keyboard_when_expense_missing(
    monkeypatch,
):
    edit_text = AsyncMock()
    edit_markup = AsyncMock()
    answer = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_text", edit_text)
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    monkeypatch.setattr(callbacks, "answer_callback", answer)
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=None),
    )

    await callbacks._handle_done_edit(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=["missing-tx"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    edit_text.assert_not_awaited()
    edit_markup.assert_awaited_once()
    kwargs = edit_markup.await_args.kwargs
    assert kwargs["reply_markup"] == {"inline_keyboard": []}
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_done_edit_without_args_strips_keyboard(monkeypatch):
    edit_markup = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_text", AsyncMock())
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    await callbacks._handle_done_edit(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=[],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    edit_markup.assert_awaited_once()
    assert edit_markup.await_args.kwargs["reply_markup"] == {"inline_keyboard": []}
