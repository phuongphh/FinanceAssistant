"""Tests for voice → intent pipeline (Story #129)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import voice_query
from backend.intent.dispatcher import DispatchOutcome, OUTCOME_EXECUTED, OUTCOME_UNCLEAR
from backend.intent.intents import IntentResult, IntentType


def _voice_message(text_voice: str = "voice123", duration: int = 10) -> dict:
    return {
        "voice": {"file_id": text_voice, "duration": duration},
        "chat": {"id": 1234},
        "from": {"id": 5678},
    }


def _user(*, wizard_state=None) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "An"
    user.wizard_state = wizard_state
    return user


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_voice_query_flows_through_intent_pipeline():
    """Voice → transcript → classify_and_dispatch."""
    user = _user()
    transcript = "tài sản của tôi có gì"

    outcome = DispatchOutcome(
        text="Net worth response",
        kind=OUTCOME_EXECUTED,
        intent=IntentType.QUERY_ASSETS,
        confidence=0.95,
    )

    with patch.object(
        voice_query, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        voice_query, "send_message", AsyncMock(return_value={"result": {"message_id": 100}})
    ), patch.object(
        voice_query, "edit_message_text", AsyncMock()
    ), patch.object(
        voice_query, "download_file", AsyncMock(return_value=b"audiobytes")
    ), patch.object(
        voice_query, "transcribe_vietnamese", AsyncMock(return_value=transcript)
    ), patch(
        "backend.bot.handlers.free_form_text.classify_and_dispatch",
        AsyncMock(return_value=outcome),
    ) as mock_pipeline:
        consumed = await voice_query.handle_voice_query(_fake_db(), _voice_message())

    assert consumed is True
    mock_pipeline.assert_awaited_once()
    kwargs = mock_pipeline.call_args.kwargs
    assert kwargs["text"] == transcript


@pytest.mark.asyncio
async def test_voice_too_long_rejected_without_transcribing():
    """≥90s voice → friendly rejection, no Whisper call."""
    user = _user()
    msg = _voice_message(duration=120)

    with patch.object(
        voice_query, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        voice_query, "send_message", AsyncMock()
    ) as mock_send, patch.object(
        voice_query, "transcribe_vietnamese", AsyncMock()
    ) as mock_trans:
        consumed = await voice_query.handle_voice_query(_fake_db(), msg)

    assert consumed is True
    mock_trans.assert_not_called()
    mock_send.assert_awaited()
    assert "dài" in mock_send.call_args.args[1]


@pytest.mark.asyncio
async def test_transcription_failure_returns_graceful_message():
    """Whisper failed → user gets "didn't catch that" not stack trace."""
    from backend.services.voice_service import VoiceTranscriptionError

    user = _user()

    with patch.object(
        voice_query, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        voice_query, "send_message", AsyncMock()
    ) as mock_send, patch.object(
        voice_query, "edit_message_text", AsyncMock()
    ), patch.object(
        voice_query, "download_file", AsyncMock(return_value=b"audio")
    ), patch.object(
        voice_query,
        "transcribe_vietnamese",
        AsyncMock(side_effect=VoiceTranscriptionError("offline")),
    ):
        consumed = await voice_query.handle_voice_query(_fake_db(), _voice_message())

    assert consumed is True
    # Last send should be the friendly error.
    last_text = mock_send.call_args.args[1]
    assert "chưa nghe được" in last_text.lower() or "thử gõ text" in last_text.lower()


@pytest.mark.asyncio
async def test_unclear_in_storytelling_mode_falls_back_to_storytelling():
    """If intent is unclear AND user is in storytelling mode → storytelling
    extracts transactions from the transcript."""
    from backend.bot.handlers import storytelling as storytelling_handlers

    user = _user(
        wizard_state={"flow": storytelling_handlers.FLOW_STORYTELLING}
    )

    outcome = DispatchOutcome(
        text="unclear msg",
        kind=OUTCOME_UNCLEAR,
        intent=IntentType.UNCLEAR,
        confidence=0.0,
    )

    with patch.object(
        voice_query, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        voice_query, "send_message", AsyncMock(return_value={"result": {"message_id": 1}})
    ), patch.object(
        voice_query, "edit_message_text", AsyncMock()
    ), patch.object(
        voice_query, "download_file", AsyncMock(return_value=b"audio")
    ), patch.object(
        voice_query, "transcribe_vietnamese", AsyncMock(return_value="hôm nay chi 200k ăn")
    ), patch(
        "backend.bot.handlers.free_form_text.classify_and_dispatch",
        AsyncMock(return_value=outcome),
    ), patch(
        "backend.bot.handlers.storytelling._process_story_text",
        AsyncMock(),
    ) as mock_story:
        consumed = await voice_query.handle_voice_query(_fake_db(), _voice_message())

    assert consumed is True
    mock_story.assert_awaited_once()


@pytest.mark.asyncio
async def test_unregistered_user_returns_false():
    """No user record → handler refuses, caller falls through."""
    with patch.object(
        voice_query, "get_user_by_telegram_id", AsyncMock(return_value=None)
    ):
        consumed = await voice_query.handle_voice_query(_fake_db(), _voice_message())
    assert consumed is False


@pytest.mark.asyncio
async def test_returns_false_when_no_voice_payload():
    """Plain text messages aren't this handler's job."""
    msg = {"chat": {"id": 1}, "from": {"id": 2}, "text": "hello"}
    consumed = await voice_query.handle_voice_query(_fake_db(), msg)
    assert consumed is False
