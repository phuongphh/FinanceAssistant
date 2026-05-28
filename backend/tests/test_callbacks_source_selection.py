"""Regression tests for the transaction-source callback flow (`txsrc:*`,
`txsrc_wallet:*`).

Issue #799 reported that after a user typed "+20 tỷ lương" → tapped
``e_wallet`` → tapped ``ZaloPay`` (callback ``txsrc_wallet:zalopay``),
the database write succeeded but no confirmation message was ever sent
back to Telegram. The user was left staring at the source-picker screen
with no feedback.

These tests pin the contract:
  - The wallet-provider branch MUST call ``edit_message_text`` to
    replace the picker with a confirmation line.
  - It MUST also fire ``answer_callback`` so the user's tap spinner
    clears.
  - The wizard state is cleared after a successful save.
  - A non-wallet source (``txsrc:cash``) follows the same contract.
  - The intermediate ``txsrc:e_wallet`` tap swaps the keyboard without
    creating an expense.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import callbacks


def _money_in_state() -> dict:
    return {
        "flow": "transaction_source_select",
        "step": "source_type",
        "draft": {
            "amount": 20_000_000_000.0,
            "merchant": "lương",
            "note": "+20 tỷ lương",
            "transaction_type": "money_in",
        },
    }


_SENTINEL = object()


def _user(state=_SENTINEL) -> MagicMock:
    """Build a fake user with ``wizard_state`` defaulting to a live
    money-in source-picker flow. Pass ``state=None`` (explicitly) to
    simulate an expired/cleared wizard."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.wizard_state = _money_in_state() if state is _SENTINEL else state
    return user


def _callback(data: str) -> dict:
    return {
        "id": "cbq-1",
        "data": data,
        "message": {"chat": {"id": 999}, "message_id": 42},
        "from": {"id": 12345},
    }


def _expense(transaction_type: str = "money_in", amount: float = 20_000_000_000.0):
    expense = SimpleNamespace(
        id=uuid.uuid4(),
        amount=amount,
        transaction_type=transaction_type,
        raw_data=None,
    )
    return expense


@pytest.mark.asyncio
async def test_txsrc_wallet_zalopay_sends_confirmation_message():
    """The bug: ``txsrc_wallet:zalopay`` wrote to DB but never edited the
    source-picker message. The user was stuck on the picker screen."""
    user = _user()
    db = MagicMock()
    expense = _expense()

    edit_text = AsyncMock(return_value={"ok": True})
    answer = AsyncMock()
    send = AsyncMock()
    with patch.object(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        callbacks.expense_service,
        "create_expense",
        AsyncMock(return_value=expense),
    ) as create, patch.object(
        callbacks, "edit_message_text", edit_text
    ), patch.object(
        callbacks, "send_message", send
    ), patch.object(
        callbacks, "answer_callback", answer
    ), patch(
        "backend.services.wizard_service.clear", AsyncMock()
    ) as wizard_clear:
        handled = await callbacks._handle_source_selection_callback(
            db, _callback("txsrc_wallet:zalopay")
        )

    assert handled is True
    create.assert_awaited_once()
    wizard_clear.assert_awaited_once()
    edit_text.assert_awaited_once()
    edit_kwargs = edit_text.await_args.kwargs
    assert edit_kwargs["chat_id"] == 999
    assert edit_kwargs["message_id"] == 42
    assert "+20,000,000,000" in edit_kwargs["text"]
    assert "ZaloPay" in edit_kwargs["text"]
    # No fallback send_message when edit succeeded.
    send.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_txsrc_wallet_falls_back_to_send_when_edit_fails():
    """Regression for #799: when ``edit_message_text`` silently returns
    ``None`` (picker message deleted, >48h old, transient Telegram 4xx),
    the handler must send a fresh confirmation so the user always gets
    feedback. Without this fallback the user is stranded on the picker
    even though the expense was written."""
    user = _user()
    db = MagicMock()
    expense = _expense()

    edit_text = AsyncMock(return_value=None)
    send = AsyncMock()
    answer = AsyncMock()
    with patch.object(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        callbacks.expense_service,
        "create_expense",
        AsyncMock(return_value=expense),
    ), patch.object(
        callbacks, "edit_message_text", edit_text
    ), patch.object(
        callbacks, "send_message", send
    ), patch.object(
        callbacks, "answer_callback", answer
    ), patch(
        "backend.services.wizard_service.clear", AsyncMock()
    ):
        await callbacks._handle_source_selection_callback(
            db, _callback("txsrc_wallet:zalopay")
        )

    edit_text.assert_awaited_once()
    send.assert_awaited_once()
    sent_chat_id, sent_text = send.await_args.args[0], send.await_args.args[1]
    assert sent_chat_id == 999
    assert "+20,000,000,000" in sent_text
    assert "ZaloPay" in sent_text
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_txsrc_wallet_uses_provider_label_for_each_wallet():
    """Every wallet provider gets a friendly label, not the raw key."""
    user = _user()
    db = MagicMock()
    expense = _expense()

    cases = [
        ("momo", "Momo"),
        ("vnpay", "VNPay"),
        ("zalopay", "ZaloPay"),
        ("viettelpay", "ViettelPay"),
    ]
    for provider, expected_label in cases:
        # Wizard state must look "active" each round because
        # ``wizard_service.clear`` is the production teardown.
        user.wizard_state = _money_in_state()
        edit_text = AsyncMock(return_value={"ok": True})
        with patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ), patch.object(
            callbacks.expense_service,
            "create_expense",
            AsyncMock(return_value=expense),
        ), patch.object(
            callbacks, "edit_message_text", edit_text
        ), patch.object(
            callbacks, "answer_callback", AsyncMock()
        ), patch(
            "backend.services.wizard_service.clear", AsyncMock()
        ):
            await callbacks._handle_source_selection_callback(
                db, _callback(f"txsrc_wallet:{provider}")
            )
        edit_text.assert_awaited_once()
        assert expected_label in edit_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_txsrc_cash_sends_confirmation_message():
    """Non-wallet source path (``txsrc:cash``) follows the same contract:
    the picker is replaced by a confirmation line."""
    user = _user()
    db = MagicMock()
    expense = _expense()

    edit_text = AsyncMock(return_value={"ok": True})
    answer = AsyncMock()
    with patch.object(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        callbacks.expense_service,
        "create_expense",
        AsyncMock(return_value=expense),
    ), patch.object(
        callbacks, "edit_message_text", edit_text
    ), patch.object(
        callbacks, "send_message", AsyncMock()
    ), patch.object(
        callbacks, "answer_callback", answer
    ), patch(
        "backend.services.wizard_service.clear", AsyncMock()
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback("txsrc:cash")
        )

    assert handled is True
    edit_text.assert_awaited_once()
    assert "Tiền mặt" in edit_text.await_args.kwargs["text"]
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_txsrc_skip_still_sends_confirmation_message():
    """``txsrc:skip`` saves the expense without a source — the picker
    must still be replaced so the user knows the write landed."""
    user = _user()
    db = MagicMock()
    expense = _expense()

    edit_text = AsyncMock(return_value={"ok": True})
    with patch.object(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        callbacks.expense_service,
        "create_expense",
        AsyncMock(return_value=expense),
    ), patch.object(
        callbacks, "edit_message_text", edit_text
    ), patch.object(
        callbacks, "send_message", AsyncMock()
    ), patch.object(
        callbacks, "answer_callback", AsyncMock()
    ), patch(
        "backend.services.wizard_service.clear", AsyncMock()
    ):
        await callbacks._handle_source_selection_callback(
            db, _callback("txsrc:skip")
        )
    edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_txsrc_e_wallet_swaps_keyboard_without_creating_expense():
    """The intermediate ``txsrc:e_wallet`` tap just replaces the keyboard
    with the wallet-provider picker. It must NOT call ``create_expense``."""
    user = _user()
    db = MagicMock()

    edit_markup = AsyncMock()
    answer = AsyncMock()
    create = AsyncMock()
    with patch.object(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        callbacks.expense_service, "create_expense", create
    ), patch.object(
        callbacks, "edit_message_reply_markup", edit_markup
    ), patch.object(
        callbacks, "answer_callback", answer
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback("txsrc:e_wallet")
        )

    assert handled is True
    create.assert_not_awaited()
    edit_markup.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_wizard_state_does_not_call_create_expense():
    """If the source-picker wizard already expired (state cleared),
    we must NOT silently create a duplicate expense."""
    user = _user(state=None)
    db = MagicMock()

    create = AsyncMock()
    answer = AsyncMock()
    with patch.object(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        callbacks.expense_service, "create_expense", create
    ), patch.object(
        callbacks, "answer_callback", answer
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback("txsrc_wallet:zalopay")
        )

    assert handled is True
    create.assert_not_awaited()
    answer.assert_awaited_once()
    assert "hết hạn" in answer.await_args.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_txsrc_credit_card_shows_all_cards_for_expense_only():
    user = _user(state={
        "flow": "transaction_source_select",
        "step": "source_type",
        "draft": {"amount": 200000.0, "transaction_type": "expense"},
    })
    db = MagicMock()
    cards = [
        SimpleNamespace(id=uuid.uuid4(), bank_name="VCB"),
        SimpleNamespace(id=uuid.uuid4(), bank_name="ACB"),
    ]
    with patch.object(callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)),          patch.object(callbacks, "list_credit_cards", AsyncMock(return_value=cards)),          patch.object(callbacks, "edit_message_reply_markup", AsyncMock()) as edit_markup,          patch.object(callbacks, "answer_callback", AsyncMock()):
        handled = await callbacks._handle_source_selection_callback(db, _callback("txsrc:credit_card"))

    assert handled is True
    kb = edit_markup.await_args.kwargs["reply_markup"]["inline_keyboard"]
    labels = [row[0]["text"] for row in kb[:2]]
    assert labels == ["💳 VCB", "💳 ACB"]


@pytest.mark.asyncio
async def test_txsrc_card_select_confirmation_mentions_bank_name():
    user = _user(state={
        "flow": "transaction_source_select",
        "step": "source_type",
        "draft": {"amount": 200000.0, "transaction_type": "expense", "merchant": "test"},
    })
    db = MagicMock()
    expense = _expense(transaction_type="expense", amount=200000.0)
    card_id = uuid.uuid4()
    card = SimpleNamespace(id=card_id, bank_name="MSB")
    with patch.object(callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)),          patch.object(callbacks, "list_credit_cards", AsyncMock(return_value=[card])),          patch.object(callbacks.expense_service, "create_expense", AsyncMock(return_value=expense)),          patch.object(callbacks, "edit_message_text", AsyncMock(return_value={"ok": True})) as edit_text,          patch.object(callbacks, "answer_callback", AsyncMock()),          patch("backend.services.wizard_service.clear", AsyncMock()):
        handled = await callbacks._handle_source_selection_callback(db, _callback(f"txsrc_card:{card_id}"))

    assert handled is True
    assert "Thẻ tín dụng MSB" in edit_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_txsrc_card_select_creates_expense_with_credit_card_source():
    user = _user(state={
        "flow": "transaction_source_select",
        "step": "source_type",
        "draft": {"amount": 200000.0, "transaction_type": "expense", "merchant": "test"},
    })
    db = MagicMock()
    expense = _expense(transaction_type="expense", amount=200000.0)
    card_id = uuid.uuid4()
    with patch.object(callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)),          patch.object(callbacks, "list_credit_cards", AsyncMock(return_value=[SimpleNamespace(id=card_id, bank_name="VCB")])),          patch.object(callbacks.expense_service, "create_expense", AsyncMock(return_value=expense)) as create,          patch.object(callbacks, "edit_message_text", AsyncMock(return_value={"ok": True})),          patch.object(callbacks, "answer_callback", AsyncMock()),          patch("backend.services.wizard_service.clear", AsyncMock()):
        handled = await callbacks._handle_source_selection_callback(db, _callback(f"txsrc_card:{card_id}"))

    assert handled is True
    payload = create.await_args.args[2]
    assert payload.source_type == "credit_card"
    assert str(payload.source_credit_card_id) == str(card_id)


@pytest.mark.asyncio
async def test_txsrc_card_select_rejects_unknown_card_id():
    user = _user(state={
        "flow": "transaction_source_select",
        "step": "source_type",
        "draft": {"amount": 200000.0, "transaction_type": "expense", "merchant": "test"},
    })
    db = MagicMock()
    card_id = uuid.uuid4()
    with patch.object(callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)),          patch.object(callbacks, "list_credit_cards", AsyncMock(return_value=[])),          patch.object(callbacks.expense_service, "create_expense", AsyncMock()) as create,          patch.object(callbacks, "answer_callback", AsyncMock()) as answer:
        handled = await callbacks._handle_source_selection_callback(db, _callback(f"txsrc_card:{card_id}"))

    assert handled is True
    create.assert_not_awaited()
    answer.assert_awaited_once()
    assert "không hợp lệ" in (answer.await_args.kwargs.get("text") or "").lower()

from backend.bot.keyboards.transaction_keyboard import transaction_source_keyboard

def test_tx_source_keyboard_expense_includes_credit_card():
    kb = transaction_source_keyboard("expense")["inline_keyboard"]
    assert any(btn["callback_data"] == "txsrc:credit_card" for row in kb for btn in row)

def test_tx_source_keyboard_money_in_excludes_credit_card():
    kb = transaction_source_keyboard("money_in")["inline_keyboard"]
    assert all(btn["callback_data"] != "txsrc:credit_card" for row in kb for btn in row)
