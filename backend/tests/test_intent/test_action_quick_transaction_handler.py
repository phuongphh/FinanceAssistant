"""Tests for ``ActionQuickTransactionHandler``.

Regression coverage for the "coming soon" bug: when the LLM classifier
labels "170k ăn trưa" as ``ACTION_QUICK_TRANSACTION``, the dispatcher
must route to this handler (not the not-implemented fallback) and the
handler must persist an expense + send the rich confirmation card.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.handlers.action_quick_transaction import (
    ActionQuickTransactionHandler,
)
from backend.intent.intents import IntentResult, IntentType


def _user() -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    return user


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_uses_classifier_amount_without_extra_llm_call():
    """When the classifier already extracted ``amount`` cleanly, the
    handler should skip the secondary LLM parse — saves a round-trip on
    the hot path.
    """
    handler = ActionQuickTransactionHandler()
    result = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.9,
        parameters={"amount": 170_000, "merchant": "ăn trưa"},
        raw_text="170k ăn trưa",
    )
    db = _fake_db()
    fake_expense = MagicMock(user_id="user-1")

    with patch(
        "backend.intent.handlers.action_quick_transaction.expense_service.create_expense",
        AsyncMock(return_value=fake_expense),
    ) as mock_create, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_confirmation",
        AsyncMock(),
    ) as mock_send, patch(
        "backend.intent.handlers.action_quick_transaction.call_llm",
        AsyncMock(),
    ) as mock_llm:
        text = await handler.handle(result, _user(), db)

    assert text == ""  # handler delivered the rich card itself
    mock_create.assert_awaited_once()
    mock_send.assert_awaited_once()
    mock_llm.assert_not_called()
    # The expense data passed to create_expense should carry the parsed
    # amount + merchant.
    args, kwargs = mock_create.call_args
    expense_data = args[2]
    assert expense_data.amount == 170_000.0
    assert expense_data.merchant == "ăn trưa"


@pytest.mark.asyncio
async def test_falls_back_to_llm_when_classifier_missed_amount():
    """If the classifier didn't extract a usable amount, the handler must
    fall back to the canonical ``parse_manual`` LLM prompt that produced
    correct expenses before the intent layer existed.
    """
    handler = ActionQuickTransactionHandler()
    result = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.85,
        parameters={},  # classifier didn't extract amount
        raw_text="vừa chi 50k cà phê",
    )
    db = _fake_db()
    fake_expense = MagicMock(user_id="user-1")

    llm_response = (
        '{"amount": 50000, "merchant": "cà phê", "is_expense": true}'
    )

    with patch(
        "backend.intent.handlers.action_quick_transaction.call_llm",
        AsyncMock(return_value=llm_response),
    ) as mock_llm, patch(
        "backend.intent.handlers.action_quick_transaction.expense_service.create_expense",
        AsyncMock(return_value=fake_expense),
    ) as mock_create, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_confirmation",
        AsyncMock(),
    ) as mock_send:
        text = await handler.handle(result, _user(), db)

    assert text == ""
    mock_llm.assert_awaited_once()
    mock_create.assert_awaited_once()
    mock_send.assert_awaited_once()
    args, _ = mock_create.call_args
    assert args[2].amount == 50_000.0
    assert args[2].merchant == "cà phê"


@pytest.mark.asyncio
async def test_returns_friendly_text_when_no_amount_can_be_parsed():
    """A non-numeric message shouldn't create an empty expense — and
    shouldn't say "coming soon" either. Return a gentle prompt so the
    user knows what's missing.
    """
    handler = ActionQuickTransactionHandler()
    result = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.85,
        parameters={},
        raw_text="hôm nay tôi mệt",
    )
    db = _fake_db()

    llm_response = '{"amount": 0, "merchant": "", "is_expense": false}'

    with patch(
        "backend.intent.handlers.action_quick_transaction.call_llm",
        AsyncMock(return_value=llm_response),
    ), patch(
        "backend.intent.handlers.action_quick_transaction.expense_service.create_expense",
        AsyncMock(),
    ) as mock_create, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_confirmation",
        AsyncMock(),
    ) as mock_send:
        text = await handler.handle(result, _user(), db)

    assert "coming soon" not in text.lower()
    assert "chưa sẵn sàng" not in text.lower()
    assert text  # non-empty hint to the user
    mock_create.assert_not_called()
    mock_send.assert_not_called()
