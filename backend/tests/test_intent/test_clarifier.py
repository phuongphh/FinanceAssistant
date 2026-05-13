"""Tests for the clarification + confirmation message builder."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.intent import clarifier
from backend.intent.intents import IntentResult, IntentType


def _user(name: str = "An") -> MagicMock:
    user = MagicMock()
    user.display_name = name
    return user


@pytest.mark.parametrize(
    "intent",
    [
        IntentType.QUERY_ASSETS,
        IntentType.QUERY_NET_WORTH,
        IntentType.QUERY_PORTFOLIO,
        IntentType.QUERY_EXPENSES,
        IntentType.QUERY_EXPENSES_BY_CATEGORY,
        IntentType.QUERY_INCOME,
        IntentType.QUERY_MARKET,
        IntentType.QUERY_GOALS,
        IntentType.ACTION_RECORD_SAVING,
        IntentType.ACTION_QUICK_TRANSACTION,
    ],
)
def test_every_clarifiable_intent_has_template(intent):
    text = clarifier.build_clarification(intent, _user())
    # Non-empty, name-substituted, has at least one bracketed option.
    assert text
    assert "An" in text
    assert "[" in text and "]" in text


def test_clarification_falls_back_for_unknown_intent():
    # GREETING isn't in the clarification map — should still produce
    # a friendly fallback rather than crashing.
    text = clarifier.build_clarification(IntentType.GREETING, _user())
    assert text
    assert "An" in text


def test_action_confirmation_includes_amount():
    intent = IntentResult(
        intent=IntentType.ACTION_RECORD_SAVING,
        confidence=0.7,
        parameters={"amount": 1_500_000},
        raw_text="tiết kiệm 1.5tr",
    )
    text = clarifier.build_action_confirmation(intent, _user("Bình"))
    assert "1,500,000" in text
    assert "Bình" in text


def test_action_confirmation_handles_quick_transaction():
    intent = IntentResult(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence=0.7,
        parameters={"amount": 200_000, "merchant": "phở"},
        raw_text="200k phở",
    )
    text = clarifier.build_action_confirmation(intent, _user())
    assert "200,000" in text
    assert "phở" in text


def test_amount_confirmation_message():
    text = clarifier.build_amount_confirmation(500_000, _user())
    assert "500,000" in text


def test_awaiting_response_uses_user_name():
    text = clarifier.build_awaiting_response(_user("Hùng"))
    assert "Hùng" in text
