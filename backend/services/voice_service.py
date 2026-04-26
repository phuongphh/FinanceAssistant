"""Voice → text via OpenAI Whisper.

Phase 3A storytelling lets the user record a voice note instead of
typing. This module owns the audio → transcript leg; the storytelling
handler then feeds the transcript into the same DeepSeek extractor as
text input.

Why OpenAI Whisper specifically:
- Vietnamese accuracy is high (better than Deepgram / Google for
  conversational southern Vietnamese in our testing)
- ~$0.006/min — for a 30-second voice note that's $0.003
- Single API key already in the OpenAI ecosystem (we already use the
  OpenAI SDK to talk to DeepSeek)

Cost guard: callers cap audio at 60 seconds upstream (Telegram voice
notes have a hard 60s limit anyway). We don't enforce here so unit
tests can exercise the full path.
"""
from __future__ import annotations

import io
import logging

from openai import AsyncOpenAI

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VoiceTranscriptionError(Exception):
    """Raised when Whisper fails or isn't configured."""


def _get_client() -> AsyncOpenAI | None:
    """Lazy-init OpenAI client so missing keys don't crash import.

    Returns ``None`` when no key is configured — callers handle the
    "voice off" path with a user-friendly message.
    """
    if not settings.openai_api_key:
        return None
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def transcribe_vietnamese(
    audio_bytes: bytes,
    *,
    filename: str = "voice.ogg",
) -> str:
    """Transcribe a Telegram voice note as Vietnamese.

    Telegram delivers voice as OGG/Opus by default — Whisper handles
    that natively, no transcoding needed.

    Returns the transcript stripped of leading/trailing whitespace.
    Raises ``VoiceTranscriptionError`` for missing config / API
    failure / empty input — caller maps these to the storytelling
    "thử lại nhé" branch.
    """
    if not audio_bytes:
        raise VoiceTranscriptionError("empty audio")

    client = _get_client()
    if client is None:
        raise VoiceTranscriptionError("OPENAI_API_KEY not configured")

    # Whisper expects a file-like object with a ``.name`` attribute so
    # the SDK can infer the format from the extension.
    buffer = io.BytesIO(audio_bytes)
    buffer.name = filename

    try:
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=buffer,
            language="vi",
            response_format="text",
        )
    except Exception as exc:  # noqa: BLE001 — surface as one error type
        logger.warning("whisper transcription failed: %s", exc)
        raise VoiceTranscriptionError(str(exc)) from exc

    transcript = (response or "").strip() if isinstance(response, str) else ""
    if not transcript:
        raise VoiceTranscriptionError("empty transcript")
    return transcript
