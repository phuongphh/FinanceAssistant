"""Tests for the Telegram entry point that drives the intent layer."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import free_form_text
from backend.intent.intents import IntentResult, IntentType


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "An"
    return user


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
async def test_handle_free_form_text_dispatches_high_confidence_intent():
    pipeline = MagicMock()
    pipeline.classify = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.QUERY_ASSETS,
            confidence=0.95,
            raw_text="tài sản",
        )
    )
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value="Assets list response")
    free_form_text.set_pipeline(pipeline)
    free_form_text.set_dispatcher(dispatcher)

    with patch.object(
        free_form_text, "send_message", AsyncMock(return_value={"ok": True})
    ) as mock_send:
        result = await free_form_text.handle_free_form_text(
            db=MagicMock(),
            chat_id=123,
            user=_user(),
            text="tài sản của tôi",
        )

    assert result is True
    mock_send.assert_awaited_once()
    args = mock_send.call_args
    assert args.args[0] == 123
    assert args.args[1] == "Assets list response"


@pytest.mark.asyncio
async def test_handle_free_form_text_returns_false_for_empty_input():
    result = await free_form_text.handle_free_form_text(
        db=MagicMock(), chat_id=1, user=_user(), text="   "
    )
    assert result is False


@pytest.mark.asyncio
async def test_handle_free_form_text_uses_unclear_response_for_oos():
    pipeline = MagicMock()
    pipeline.classify = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.OUT_OF_SCOPE,
            confidence=0.9,
            raw_text="thời tiết",
        )
    )
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value="OOS response")
    free_form_text.set_pipeline(pipeline)
    free_form_text.set_dispatcher(dispatcher)

    with patch.object(
        free_form_text, "send_message", AsyncMock(return_value={"ok": True})
    ) as mock_send:
        result = await free_form_text.handle_free_form_text(
            db=MagicMock(),
            chat_id=99,
            user=_user(),
            text="thời tiết hôm nay",
        )

    assert result is True
    mock_send.assert_awaited_once_with(99, "OOS response")
