"""Voice → text via the self-hosted STT provider (``stt.nuitruc.ai``).

Phase 3A storytelling lets the user record a voice note instead of
typing. This module owns the audio → transcript leg; the storytelling
handler then feeds the transcript into the same DeepSeek extractor as
text input.

Why a dedicated Vietnamese STT endpoint (replacing Whisper):
- Vietnamese accuracy is materially better than Whisper-1 on
  conversational southern accents in our testing
- Self-hosted — no per-minute cost, no third-party data leak
- OGG/Opus (Telegram's native voice format) is accepted natively, no
  transcoding needed

Public contract is unchanged: callers still get a ``str`` transcript or
a ``VoiceTranscriptionError`` — the storytelling/voice_query handlers
need no changes.
"""
from __future__ import annotations

import json
import logging

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VoiceTranscriptionError(Exception):
    """Raised when the STT provider fails or returns no transcript."""


# Singleton client — HTTP/2 + connection pool reuse keeps cold-start
# latency low across consecutive voice notes (e.g. quick back-to-back
# storytelling messages). Lazily constructed so importing this module in
# tests / CLI doesn't open sockets.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.stt_api_timeout_seconds, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            http2=True,
        )
    return _client


def _mime_for(filename: str) -> str:
    """Best-effort content-type from filename extension.

    The provider sniffs the audio itself, but a correct content-type
    helps when a proxy in front of it inspects the upload.
    """
    lower = filename.lower()
    if lower.endswith(".ogg") or lower.endswith(".oga") or lower.endswith(".opus"):
        return "audio/ogg"
    if lower.endswith(".mp3"):
        return "audio/mpeg"
    if lower.endswith(".wav"):
        return "audio/wav"
    if lower.endswith(".m4a") or lower.endswith(".mp4"):
        return "audio/mp4"
    if lower.endswith(".webm"):
        return "audio/webm"
    return "application/octet-stream"


async def transcribe_vietnamese(
    audio_bytes: bytes,
    *,
    filename: str = "voice.ogg",
) -> str:
    """Transcribe a Telegram voice note as Vietnamese.

    Returns the transcript stripped of leading/trailing whitespace.
    Raises ``VoiceTranscriptionError`` for empty input, transport
    failure, non-2xx response, malformed body, or an empty transcript —
    the caller maps these to the storytelling "thử lại nhé" branch.
    """
    if not audio_bytes:
        raise VoiceTranscriptionError("empty audio")

    headers: dict[str, str] = {"accept": "application/json"}
    if settings.stt_api_key:
        headers["Authorization"] = f"Bearer {settings.stt_api_key}"

    files = {"file": (filename, audio_bytes, _mime_for(filename))}

    client = _get_client()
    try:
        resp = await client.post(settings.stt_api_url, headers=headers, files=files)
    except httpx.TimeoutException as exc:
        # Log size only — never the audio itself.
        logger.warning("STT provider timeout (audio_size=%d)", len(audio_bytes))
        raise VoiceTranscriptionError("STT provider timeout") from exc
    except httpx.HTTPError as exc:
        logger.warning("STT provider transport error: %s", exc)
        raise VoiceTranscriptionError(f"STT provider error: {exc}") from exc

    if resp.status_code >= 400:
        # Body may include validation hints; keep first 200 chars at debug.
        logger.error("STT provider HTTP %d", resp.status_code)
        logger.debug("STT provider body: %s", resp.text[:200])
        raise VoiceTranscriptionError(f"STT provider HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("STT provider returned non-JSON body")
        raise VoiceTranscriptionError("STT provider returned non-JSON") from exc

    transcript = ""
    if isinstance(payload, dict):
        raw = payload.get("transcript") or payload.get("text") or ""
        if isinstance(raw, str):
            transcript = raw.strip()

    if not transcript:
        raise VoiceTranscriptionError("empty transcript")

    logger.info(
        "STT transcribed: audio_size=%d transcript_len=%d processing_time=%s",
        len(audio_bytes),
        len(transcript),
        payload.get("processing_time_seconds") if isinstance(payload, dict) else None,
    )
    return transcript
