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
    db.get = AsyncMock(return_value=None)
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

    llm_response = '{"amount": 50000, "merchant": "cà phê", "is_expense": true}'

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


@pytest.mark.asyncio
async def test_splits_multiple_expenses_in_one_message_without_llm():
    """Messages with multiple amount tokens should create one expense per item."""
    handler = ActionQuickTransactionHandler()
    result = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.9,
        parameters={"amount": 100_000, "merchant": "tiền xăng, ăn trưa"},
        raw_text="Tối qua tiền xăng 50k, ăn trưa 50k",
    )
    db = _fake_db()
    fake_expenses = [MagicMock(user_id="user-1"), MagicMock(user_id="user-1")]

    with patch(
        "backend.intent.handlers.action_quick_transaction.expense_service.create_expense",
        AsyncMock(side_effect=fake_expenses),
    ) as mock_create, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_confirmation",
        AsyncMock(),
    ) as mock_send_single, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_batch_confirmation",
        AsyncMock(),
    ) as mock_send_batch, patch(
        "backend.intent.handlers.action_quick_transaction.call_llm",
        AsyncMock(),
    ) as mock_llm:
        text = await handler.handle(result, _user(), db)

    assert text == ""
    assert mock_create.await_count == 2
    mock_send_single.assert_not_called()
    mock_send_batch.assert_awaited_once()
    mock_llm.assert_not_called()

    first = mock_create.await_args_list[0].args[2]
    second = mock_create.await_args_list[1].args[2]
    assert first.amount == 50_000.0
    assert first.merchant == "tiền xăng"
    assert first.category == "transport"
    assert first.raw_data["batch_id"] == second.raw_data["batch_id"]
    assert second.amount == 50_000.0
    assert second.merchant == "ăn trưa"
    assert second.category == "food"


@pytest.mark.asyncio
async def test_keeps_single_total_message_as_one_expense():
    """One total amount for multiple nouns should remain one expense."""
    handler = ActionQuickTransactionHandler()
    result = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.9,
        parameters={"amount": 400_000, "merchant": "ăn tối và trà sữa"},
        raw_text="Tối qua ăn tối và trà sữa 400k",
    )
    db = _fake_db()
    fake_expense = MagicMock(user_id="user-1")

    with patch(
        "backend.intent.handlers.action_quick_transaction.expense_service.create_expense",
        AsyncMock(return_value=fake_expense),
    ) as mock_create, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_confirmation",
        AsyncMock(),
    ) as mock_send_single, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_batch_confirmation",
        AsyncMock(),
    ) as mock_send_batch:
        text = await handler.handle(result, _user(), db)

    assert text == ""
    mock_create.assert_awaited_once()
    mock_send_single.assert_awaited_once()
    mock_send_batch.assert_not_called()
    expense_data = mock_create.call_args.args[2]
    assert expense_data.amount == 400_000.0
    assert expense_data.merchant == "ăn tối và trà sữa"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text",
    [
        "Hôm nay nhận lương 20tr vào tiền mặt",
        "Nhận thưởng tết 50tr",
        "Được thưởng 5tr",
        "Lãi ngân hàng 200k tháng này",
        "Freelance 3tr về tài khoản",
        "Cổ tức 1tr",
        # Wallet top-up shapes — caught by code review on PR #669. Used
        # to silently route to expense because verbs (thêm/cộng/nạp)
        # aren't in _INCOME_KEYWORDS. The wallet/account preposition
        # ("vào ví/tài khoản") plus the named destination is the
        # disambiguating signal.
        "thêm 3tr vào ví momo",
        "cộng 2tr vào tài khoản VCB",
        "nạp 500k vào cash",
        "nhận 5tr vào ví zalopay",
    ],
)
async def test_income_messages_are_not_recorded_as_expense(raw_text):
    """Issues #656, #661: messages with income verbs must NOT create an
    expense row. The handler returns a clarification pointing to the
    income flow instead.
    """
    handler = ActionQuickTransactionHandler()
    result = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.85,
        parameters={},
        raw_text=raw_text,
    )
    db = _fake_db()

    with patch(
        "backend.intent.handlers.action_quick_transaction.expense_service.create_expense",
        AsyncMock(),
    ) as mock_create, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_confirmation",
        AsyncMock(),
    ) as mock_send, patch(
        "backend.intent.handlers.action_quick_transaction.call_llm",
        AsyncMock(),
    ) as mock_llm:
        text = await handler.handle(result, _user(), db)

    mock_create.assert_not_called()
    mock_send.assert_not_called()
    mock_llm.assert_not_called()
    assert text
    # The reply should mention income (thu nhập / lương / thưởng) so the
    # user understands why nothing was recorded.
    lowered = text.lower()
    assert any(kw in lowered for kw in ("thu nhập", "lương", "thưởng", "income"))


@pytest.mark.asyncio
async def test_income_verb_with_spending_context_still_records_expense():
    """Mixed sentence: "lương tháng này tiêu hết 5tr" — the expense verb
    "tiêu" wins, so we DO record an expense. Guards the income check
    from being too greedy.
    """
    handler = ActionQuickTransactionHandler()
    result = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.85,
        parameters={"amount": 5_000_000, "merchant": "tiêu hết"},
        raw_text="lương tháng này tiêu hết 5tr",
    )
    db = _fake_db()
    fake_expense = MagicMock(user_id="user-1")

    with patch(
        "backend.intent.handlers.action_quick_transaction.expense_service.create_expense",
        AsyncMock(return_value=fake_expense),
    ) as mock_create, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_confirmation",
        AsyncMock(),
    ):
        await handler.handle(result, _user(), db)

    mock_create.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text,should_record",
    [
        # "thường" (often) collides with "thưởng" (bonus) after diacritic
        # stripping. PR #662 review: ordinary expenses with "thường"
        # must still record.
        ("thường ăn sáng 50k", True),
        ("mình thường mua cà phê 35k", True),
        # "trả lương" — the income guard must hold even though the
        # message contains the spending-flavored verb "trả".
        ("công ty trả lương 20tr", False),
    ],
)
async def test_diacritic_collisions_do_not_break_income_guard(
    raw_text, should_record
):
    """PR #662 review (chatgpt-codex): bare "thuong"/"tra" collide with
    unrelated words after diacritic stripping. The keyword lists must
    avoid those collisions.
    """
    handler = ActionQuickTransactionHandler()
    result = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.85,
        parameters={"amount": 50_000, "merchant": "ăn sáng"} if should_record else {},
        raw_text=raw_text,
    )
    db = _fake_db()
    fake_expense = MagicMock(user_id="user-1")

    with patch(
        "backend.intent.handlers.action_quick_transaction.expense_service.create_expense",
        AsyncMock(return_value=fake_expense),
    ) as mock_create, patch(
        "backend.intent.handlers.action_quick_transaction.send_transaction_confirmation",
        AsyncMock(),
    ), patch(
        "backend.intent.handlers.action_quick_transaction.call_llm",
        AsyncMock(
            return_value='{"is_expense": true, "amount": 50000, "merchant": "ăn sáng"}'
        ),
    ):
        await handler.handle(result, _user(), db)

    if should_record:
        mock_create.assert_awaited_once()
    else:
        mock_create.assert_not_called()
