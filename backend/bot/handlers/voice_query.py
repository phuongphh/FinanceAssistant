"""Voice → intent pipeline (Phase 3.5 Story #129).

Outside of storytelling mode a voice note SHOULD be a query, not a
transaction-extraction blob. This module handles that case:

  1. Download the OGG from Telegram.
  2. Whisper-transcribe to Vietnamese text.
  3. Echo "🎤 Mình nghe: <transcript>" so the user can correct
     misheard input quickly.
  4. Feed the transcript through the intent pipeline.
  5. If the result is UNCLEAR and the user has wizard_state suggesting
     storytelling intent, fall back to the storytelling handler so a
     mis-typed mode still works.

Wired into the worker BEFORE the storytelling-voice branch — the
storytelling branch only fires when ``wizard_state.flow ==
FLOW_STORYTELLING``, so the order is: storytelling first, then this.
The worker change keeps the precedence explicit.

Cost note: Whisper at $0.006/min × ~30s = $0.003/call. We cap at 90s
(matches storytelling cap) to keep the upper bound at $0.009/call.
"""
from __future__ import annotations

import html
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.handlers import free_form_text as intent_layer
from backend.intent.intents import IntentType
from backend.models.user import User
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    download_file,
    edit_message_text,
    send_message,
)
from backend.services.voice_service import (
    VoiceTranscriptionError,
    transcribe_vietnamese,
)

logger = logging.getLogger(__name__)


MAX_VOICE_DURATION_SECONDS = 90

# Analytics events — separate from the storytelling voice events so the
# admin dashboard can chart "free-form voice queries" independently.
EVENT_VOICE_QUERY_RECEIVED = "voice_query_received"
EVENT_VOICE_QUERY_FAILED = "voice_query_failed"


async def handle_voice_query(db: AsyncSession, message: dict) -> bool:
    """Consume a voice message as a free-form query.

    Returns ``True`` once a reply has been sent. Returns ``False`` only
    when there's no voice payload to process (caller falls through).
    The caller is the worker; ``message`` is the raw Telegram update.
    """
    voice = message.get("voice")
    if not voice:
        return False

    chat_id = (message.get("chat") or {}).get("id")
    telegram_id = (message.get("from") or {}).get("id")
    if chat_id is None or telegram_id is None:
        return False

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        # Unregistered users can't run queries — defer to the existing
        # /start flow rather than transcribing for a phantom user.
        return False

    duration = voice.get("duration") or 0
    if duration > MAX_VOICE_DURATION_SECONDS:
        await send_message(
            chat_id,
            "🎤 Voice hơi dài rồi 😅\n"
            f"Bạn thử lại với clip ngắn hơn {MAX_VOICE_DURATION_SECONDS} giây nhé.",
        )
        analytics.track(
            EVENT_VOICE_QUERY_FAILED,
            user_id=user.id,
            properties={"reason": "too_long", "duration_s": int(duration)},
        )
        return True

    file_id = voice.get("file_id")
    if not file_id:
        analytics.track(
            EVENT_VOICE_QUERY_FAILED,
            user_id=user.id,
            properties={"reason": "missing_file_id"},
        )
        return False

    processing = await send_message(chat_id, "🎤 Đang nghe bạn...")

    audio_bytes = await download_file(file_id)
    if not audio_bytes:
        await send_message(
            chat_id,
            "Mình không tải được voice 😔 Thử lại hoặc gõ text nhé?",
        )
        analytics.track(
            EVENT_VOICE_QUERY_FAILED,
            user_id=user.id,
            properties={"reason": "download_failed"},
        )
        return True

    try:
        transcript = await transcribe_vietnamese(
            audio_bytes, filename="voice.ogg"
        )
    except VoiceTranscriptionError as exc:
        logger.warning("voice query: transcription failed: %s", exc)
        await send_message(
            chat_id,
            "Mình chưa nghe được rõ 😔\n"
            "Bạn thử gõ text nhé — mình hiểu cả cách viết tự nhiên.",
        )
        analytics.track(
            EVENT_VOICE_QUERY_FAILED,
            user_id=user.id,
            properties={"reason": "whisper_failed"},
        )
        return True

    analytics.track(
        EVENT_VOICE_QUERY_RECEIVED,
        user_id=user.id,
        properties={"duration_s": int(duration), "chars": len(transcript)},
    )

    # Echo the transcript so the user can spot-check Whisper's read.
    transcript_msg = f"🎤 Mình nghe: <i>{html.escape(transcript)}</i>"
    msg_id = _extract_message_id(processing)
    edited = False
    if msg_id:
        try:
            await edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=transcript_msg,
                parse_mode="HTML",
                reply_markup=None,
            )
            edited = True
        except Exception:
            logger.debug("voice query: edit transcript failed", exc_info=True)
    if not edited:
        await send_message(chat_id, transcript_msg, parse_mode="HTML")

    # Run the transcript through the intent pipeline.
    outcome = await intent_layer.classify_and_dispatch(
        db=db, chat_id=chat_id, user=user, text=transcript,
    )

    # Storytelling fallback — if the intent layer couldn't classify
    # AND the user is mid-storytelling, hand the transcript to the
    # storytelling extractor instead. Note: we explicitly check the
    # wizard_state flow rather than re-fetching the user because the
    # state we saw at function entry is the source of truth for this
    # message.
    if outcome is None or _looks_unclear(outcome):
        from backend.bot.handlers import storytelling as storytelling_handlers

        if (user.wizard_state or {}).get(
            "flow"
        ) == storytelling_handlers.FLOW_STORYTELLING:
            await storytelling_handlers._process_story_text(
                db, chat_id, user, transcript, source_kind="voice",
            )
    return True


def _looks_unclear(outcome) -> bool:
    """A dispatch outcome counts as unclear when intent is UNCLEAR."""
    return getattr(outcome, "intent", None) == IntentType.UNCLEAR


def _extract_message_id(send_result: dict | None) -> int | None:
    """Pull message_id out of the Telegram sendMessage response."""
    if not isinstance(send_result, dict):
        return None
    payload = send_result.get("result") if "result" in send_result else send_result
    if not isinstance(payload, dict):
        return None
    msg_id = payload.get("message_id")
    return int(msg_id) if isinstance(msg_id, int) else None


__all__ = [
    "EVENT_VOICE_QUERY_FAILED",
    "EVENT_VOICE_QUERY_RECEIVED",
    "MAX_VOICE_DURATION_SECONDS",
    "handle_voice_query",
]
