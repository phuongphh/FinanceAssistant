"""Tests for the IntentDispatcher confidence policy + handler routing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.intent.dispatcher import (
    CONFIRM_THRESHOLD,
    EXECUTE_THRESHOLD,
    IntentDispatcher,
    READ_INTENTS,
)
from backend.intent.intents import IntentResult, IntentType


def _user(name: str = "Bé Tiền") -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    user.display_name = name
    user.monthly_income = None
    return user


@pytest.fixture
def dispatcher() -> IntentDispatcher:
    return IntentDispatcher()


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


@pytest.mark.asyncio
async def test_meta_intent_uses_dedicated_handler(dispatcher, db):
    result = IntentResult(
        intent=IntentType.GREETING, confidence=0.95, raw_text="chào"
    )
    response = await dispatcher.dispatch(result, _user(), db)
    assert "chào" in response.lower()


@pytest.mark.asyncio
async def test_unclear_intent_below_threshold_uses_unclear_handler(
    dispatcher, db
):
    result = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=CONFIRM_THRESHOLD - 0.01,
        raw_text="???",
    )
    response = await dispatcher.dispatch(result, _user("An"), db)
    assert "chưa hiểu" in response.lower() or "thử hỏi" in response.lower()


@pytest.mark.asyncio
async def test_write_intent_at_medium_confidence_falls_to_unclear(
    dispatcher, db
):
    """Confidence in 0.5–0.8 for an action_* intent must NOT execute
    until the confirm flow lands in Epic 2."""
    result = IntentResult(
        intent=IntentType.ACTION_RECORD_SAVING,
        confidence=0.65,
        parameters={"amount": 1_000_000},
        raw_text="tiết kiệm 1tr",
    )
    response = await dispatcher.dispatch(result, _user(), db)
    assert "chưa hiểu" in response.lower() or "thử hỏi" in response.lower()


@pytest.mark.asyncio
async def test_read_intent_at_medium_confidence_executes(dispatcher, db):
    """Read intents are safe — execute even at medium confidence."""
    # Patch the handler to verify it actually got called.
    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(return_value="OK")
    dispatcher._handlers[IntentType.QUERY_ASSETS] = fake_handler

    result = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.65,
        raw_text="tài sản",
    )
    response = await dispatcher.dispatch(result, _user(), db)
    assert response == "OK"
    fake_handler.handle.assert_awaited_once()


@pytest.mark.asyncio
async def test_handler_exception_is_swallowed_to_friendly_message(
    dispatcher, db
):
    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(side_effect=RuntimeError("boom"))
    dispatcher._handlers[IntentType.QUERY_ASSETS] = fake_handler

    result = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.95,
        raw_text="tài sản",
    )
    response = await dispatcher.dispatch(result, _user(), db)
    assert "lỗi" in response.lower() or "thử lại" in response.lower()


@pytest.mark.asyncio
async def test_unknown_handler_returns_coming_soon(dispatcher, db):
    # ADVISORY has no handler in Epic 1.
    result = IntentResult(
        intent=IntentType.ADVISORY,
        confidence=0.9,
        raw_text="nên đầu tư gì",
    )
    response = await dispatcher.dispatch(result, _user(), db)
    assert "coming soon" in response.lower()


def test_thresholds_have_sane_ordering():
    assert 0 < CONFIRM_THRESHOLD < EXECUTE_THRESHOLD <= 1


def test_read_intents_set_includes_all_query_intents():
    expected = {
        IntentType.QUERY_ASSETS,
        IntentType.QUERY_NET_WORTH,
        IntentType.QUERY_PORTFOLIO,
        IntentType.QUERY_EXPENSES,
        IntentType.QUERY_EXPENSES_BY_CATEGORY,
        IntentType.QUERY_INCOME,
        IntentType.QUERY_CASHFLOW,
        IntentType.QUERY_MARKET,
        IntentType.QUERY_GOALS,
        IntentType.QUERY_GOAL_PROGRESS,
    }
    assert expected.issubset(READ_INTENTS)
