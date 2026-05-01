"""Tests for the IntentDispatcher confidence policy + handler routing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.intent.dispatcher import (
    CONFIRM_THRESHOLD,
    DispatchOutcome,
    EXECUTE_THRESHOLD,
    IntentDispatcher,
    OUTCOME_CLARIFY_SENT,
    OUTCOME_CONFIRM_SENT,
    OUTCOME_ERROR,
    OUTCOME_EXECUTED,
    OUTCOME_NOT_IMPLEMENTED,
    OUTCOME_OUT_OF_SCOPE,
    OUTCOME_UNCLEAR,
    READ_INTENTS,
    WRITE_INTENTS,
)
from backend.intent.intents import IntentResult, IntentType


def _user(name: str = "Bé Tiền") -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    user.display_name = name
    user.monthly_income = None
    user.wizard_state = None
    return user


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def dispatcher() -> IntentDispatcher:
    return IntentDispatcher()


@pytest.fixture
def db():
    return _fake_db()


@pytest.mark.asyncio
async def test_greeting_uses_meta_handler(dispatcher, db):
    result = IntentResult(
        intent=IntentType.GREETING, confidence=0.95, raw_text="chào"
    )
    outcome = await dispatcher.dispatch(result, _user(), db)
    assert isinstance(outcome, DispatchOutcome)
    assert outcome.kind == OUTCOME_EXECUTED
    assert "chào" in outcome.text.lower()


@pytest.mark.asyncio
async def test_unclear_intent_returns_unclear_outcome(dispatcher, db):
    result = IntentResult(
        intent=IntentType.UNCLEAR, confidence=0.0, raw_text="???"
    )
    outcome = await dispatcher.dispatch(result, _user("An"), db)
    assert outcome.kind == OUTCOME_UNCLEAR
    assert (
        "chưa hiểu" in outcome.text.lower()
        or "thử hỏi" in outcome.text.lower()
    )


@pytest.mark.asyncio
async def test_low_confidence_known_intent_triggers_clarification(dispatcher, db):
    """At confidence <0.5 with a known intent, clarification message
    should be sent + state persisted."""
    result = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.4,
        raw_text="tài sản gì đó",
    )
    outcome = await dispatcher.dispatch(result, _user(), db)
    assert outcome.kind == OUTCOME_CLARIFY_SENT
    assert outcome.inline_keyboard_hint  # buttons extracted from YAML


@pytest.mark.asyncio
async def test_write_intent_at_medium_confidence_triggers_confirmation(
    dispatcher, db
):
    """0.5–0.8 + write intent → confirmation, NOT execution."""
    result = IntentResult(
        intent=IntentType.ACTION_RECORD_SAVING,
        confidence=0.65,
        parameters={"amount": 1_000_000},
        raw_text="tiết kiệm 1tr",
    )
    outcome = await dispatcher.dispatch(result, _user(), db)
    assert outcome.kind == OUTCOME_CONFIRM_SENT
    assert outcome.inline_keyboard_hint == ["✅ Đúng", "❌ Không phải"]
    assert "1,000,000" in outcome.text


@pytest.mark.asyncio
async def test_write_intent_missing_params_falls_to_clarification(dispatcher, db):
    """Even at high confidence, a write intent without required params
    should clarify instead of confirming an empty action."""
    result = IntentResult(
        intent=IntentType.ACTION_RECORD_SAVING,
        confidence=0.7,
        parameters={},
        raw_text="tiết kiệm",
    )
    outcome = await dispatcher.dispatch(result, _user(), db)
    assert outcome.kind == OUTCOME_CLARIFY_SENT


@pytest.mark.asyncio
async def test_read_intent_at_medium_confidence_executes(dispatcher, db):
    """Read intents are safe — execute even at medium confidence."""
    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(return_value="OK")
    dispatcher._handlers[IntentType.QUERY_ASSETS] = fake_handler

    result = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.65,
        raw_text="tài sản",
    )
    outcome = await dispatcher.dispatch(result, _user(), db)
    assert outcome.kind == OUTCOME_EXECUTED
    assert outcome.text == "OK"
    fake_handler.handle.assert_awaited_once()


@pytest.mark.asyncio
async def test_handler_exception_returns_friendly_error(dispatcher, db):
    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(side_effect=RuntimeError("boom"))
    dispatcher._handlers[IntentType.QUERY_ASSETS] = fake_handler

    result = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.95,
        raw_text="tài sản",
    )
    outcome = await dispatcher.dispatch(result, _user(), db)
    assert outcome.kind == OUTCOME_ERROR
    assert "lỗi" in outcome.text.lower() or "thử lại" in outcome.text.lower()


@pytest.mark.asyncio
async def test_unknown_handler_returns_not_implemented(dispatcher, db):
    """ADVISORY has no handler in Epic 1 — gracefully say so."""
    result = IntentResult(
        intent=IntentType.ADVISORY,
        confidence=0.9,
        raw_text="nên đầu tư gì",
    )
    outcome = await dispatcher.dispatch(result, _user(), db)
    assert outcome.kind == OUTCOME_NOT_IMPLEMENTED
    assert "coming soon" in outcome.text.lower()


@pytest.mark.asyncio
async def test_oos_returns_oos_outcome(dispatcher, db):
    result = IntentResult(
        intent=IntentType.OUT_OF_SCOPE,
        confidence=0.9,
        raw_text="thời tiết hôm nay",
    )
    outcome = await dispatcher.dispatch(result, _user(), db)
    assert outcome.kind == OUTCOME_OUT_OF_SCOPE


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


def test_write_intents_set_excludes_reads():
    assert WRITE_INTENTS.isdisjoint(READ_INTENTS)
    assert IntentType.ACTION_RECORD_SAVING in WRITE_INTENTS
    assert IntentType.ACTION_QUICK_TRANSACTION in WRITE_INTENTS
