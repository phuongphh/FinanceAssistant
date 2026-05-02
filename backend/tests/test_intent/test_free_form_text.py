"""Tests for the Telegram entry point that drives the intent layer."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import free_form_text
from backend.intent.dispatcher import (
    DispatchOutcome,
    OUTCOME_CLARIFY_SENT,
    OUTCOME_CONFIRM_SENT,
    OUTCOME_EXECUTED,
    OUTCOME_OUT_OF_SCOPE,
)
from backend.intent.intents import IntentResult, IntentType


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "An"
    user.wizard_state = None
    return user


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def _restore_singletons():
    """Each test gets a fresh stub pair; restore at the end so other
    tests see the real pipeline + dispatcher."""
    real_pipeline = free_form_text._pipeline
    real_dispatcher = free_form_text._dispatcher
    yield
    free_form_text.set_pipeline(real_pipeline)
    free_form_text.set_dispatcher(real_dispatcher)


@pytest.mark.asyncio
async def test_dispatches_high_confidence_intent_with_no_keyboard():
    pipeline = MagicMock()
    pipeline.classify = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.QUERY_ASSETS,
            confidence=0.95,
            raw_text="tài sản",
        )
    )
    pipeline.llm_classifier = None  # so _track_classification short-circuits cleanly

    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(
        return_value=DispatchOutcome(
            text="Assets list response",
            kind=OUTCOME_EXECUTED,
            intent=IntentType.QUERY_ASSETS,
            confidence=0.95,
        )
    )
    free_form_text.set_pipeline(pipeline)
    free_form_text.set_dispatcher(dispatcher)

    with patch.object(
        free_form_text, "send_message", AsyncMock(return_value={"ok": True})
    ) as mock_send:
        result = await free_form_text.handle_free_form_text(
            db=_fake_db(),
            chat_id=123,
            user=_user(),
            text="tài sản của tôi",
        )

    assert result is True
    mock_send.assert_awaited_once()
    args, kwargs = mock_send.call_args
    assert args[0] == 123
    assert args[1] == "Assets list response"
    # Reads have no inline keyboard.
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_clarification_outcome_attaches_inline_keyboard():
    pipeline = MagicMock()
    pipeline.classify = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.QUERY_ASSETS,
            confidence=0.4,
            raw_text="tài sản gì",
        )
    )
    pipeline.llm_classifier = None
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(
        return_value=DispatchOutcome(
            text="Bạn muốn xem... [📊 Tổng] [🏠 BĐS]",
            kind=OUTCOME_CLARIFY_SENT,
            intent=IntentType.QUERY_ASSETS,
            confidence=0.4,
            inline_keyboard_hint=["📊 Tổng", "🏠 BĐS"],
        )
    )
    free_form_text.set_pipeline(pipeline)
    free_form_text.set_dispatcher(dispatcher)

    with patch.object(
        free_form_text, "send_message", AsyncMock(return_value={"ok": True})
    ) as mock_send:
        await free_form_text.handle_free_form_text(
            db=_fake_db(), chat_id=1, user=_user(), text="tài sản gì",
        )

    keyboard = mock_send.call_args.kwargs.get("reply_markup")
    assert keyboard is not None
    assert "inline_keyboard" in keyboard
    # Two buttons each on their own row.
    assert len(keyboard["inline_keyboard"]) == 2
    assert keyboard["inline_keyboard"][0][0]["text"] == "📊 Tổng"


@pytest.mark.asyncio
async def test_confirmation_outcome_attaches_yes_no_keyboard():
    pipeline = MagicMock()
    pipeline.classify = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.ACTION_RECORD_SAVING,
            confidence=0.7,
            parameters={"amount": 1_000_000},
            raw_text="tiết kiệm 1tr",
        )
    )
    pipeline.llm_classifier = None
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(
        return_value=DispatchOutcome(
            text="Mình hiểu bạn muốn ghi tiết kiệm 1,000,000đ — đúng không?",
            kind=OUTCOME_CONFIRM_SENT,
            intent=IntentType.ACTION_RECORD_SAVING,
            confidence=0.7,
        )
    )
    free_form_text.set_pipeline(pipeline)
    free_form_text.set_dispatcher(dispatcher)

    with patch.object(
        free_form_text, "send_message", AsyncMock(return_value={"ok": True})
    ) as mock_send:
        await free_form_text.handle_free_form_text(
            db=_fake_db(), chat_id=1, user=_user(), text="tiết kiệm 1tr"
        )

    keyboard = mock_send.call_args.kwargs.get("reply_markup")
    assert keyboard is not None
    labels = [
        btn["text"] for row in keyboard["inline_keyboard"] for btn in row
    ]
    assert labels == ["✅ Đúng", "❌ Không phải"]


@pytest.mark.asyncio
async def test_returns_false_for_empty_input():
    result = await free_form_text.handle_free_form_text(
        db=_fake_db(), chat_id=1, user=_user(), text="   "
    )
    assert result is False


@pytest.mark.asyncio
async def test_oos_outcome_sends_response_without_keyboard():
    pipeline = MagicMock()
    pipeline.classify = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.OUT_OF_SCOPE,
            confidence=0.9,
            raw_text="thời tiết",
        )
    )
    pipeline.llm_classifier = None
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(
        return_value=DispatchOutcome(
            text="OOS response",
            kind=OUTCOME_OUT_OF_SCOPE,
            intent=IntentType.OUT_OF_SCOPE,
            confidence=0.9,
        )
    )
    free_form_text.set_pipeline(pipeline)
    free_form_text.set_dispatcher(dispatcher)

    with patch.object(
        free_form_text, "send_message", AsyncMock(return_value={"ok": True})
    ) as mock_send:
        result = await free_form_text.handle_free_form_text(
            db=_fake_db(), chat_id=99, user=_user(), text="thời tiết hôm nay",
        )

    assert result is True
    args = mock_send.call_args
    assert args.args == (99, "OOS response")
    assert args.kwargs.get("reply_markup") is None
