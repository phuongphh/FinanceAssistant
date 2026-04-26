"""Storytelling expense capture — text + voice input handler.

Flow (P3A-18):

    1. User opens storytelling mode via:
       - tap "💬 Kể chuyện" on morning briefing  (P3A-20 wires this)
       - /story or /kechuyen command
    2. Bot prompts the user, sets ``wizard_state`` to record the mode +
       per-user threshold + originating source.
    3. User sends text OR a voice note. Voice path: Telegram getFile →
       Whisper → transcript echo, then identical to text path.
    4. extract_transactions_from_story → StorytellingResult.
    5. Pending transactions are stored in ``wizard_state.draft`` and the
       confirmation message + inline keyboard (built by P3A-19) is sent.

State shape on ``users.wizard_state``::

    {
      "flow": "storytelling",
      "step": "awaiting_story" | "confirm_pending",
      "draft": {
        "started_at": "2026-04-26T07:30:00+00:00",
        "source": "from_briefing" | "direct_command",
        "threshold": 200000,
        "pending": [...transactions...]   # only after extract
      }
    }

Layer contract: this handler reads/mutates DB through services
(``wizard_service``, ``threshold_service``) and never commits — the
worker owns the transaction boundary.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from datetime import date

from backend import analytics
from backend.bot.formatters.money import format_money_short
from backend.bot.keyboards.common import parse_callback
from backend.bot.personality.storytelling_prompt import (
    StorytellingResult,
    extract_transactions_from_story,
)
from backend.config.categories import get_category
from backend.models.user import User
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service, wizard_service
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    answer_callback,
    download_file,
    edit_message_reply_markup,
    edit_message_text,
    send_message,
)
from backend.services.voice_service import (
    VoiceTranscriptionError,
    transcribe_vietnamese,
)

logger = logging.getLogger(__name__)


# ---------- Constants -------------------------------------------------

FLOW_STORYTELLING = "storytelling"

STEP_AWAITING_STORY = "awaiting_story"
STEP_CONFIRM_PENDING = "confirm_pending"

SOURCE_FROM_BRIEFING = "from_briefing"
SOURCE_DIRECT_COMMAND = "direct_command"

# Auto-exit window — if the user opened storytelling mode and never
# replied, drop the mode after 10 minutes so a stale "Kể mình nghe..."
# prompt doesn't swallow an unrelated message later.
STORYTELLING_TIMEOUT = timedelta(minutes=10)

# Telegram voice notes are capped at 60s by the client. Whisper handles
# longer just fine but we reject upfront so a user fumbling with
# audio_file uploads doesn't burn $0.10 of API budget on a podcast.
MAX_VOICE_DURATION_SECONDS = 90


class StorytellingEvent:
    """Analytics event names for the storytelling funnel."""
    OPENED = "storytelling_opened"
    OPENED_FROM_BRIEFING = "storytelling_from_briefing"
    OPENED_DIRECT = "storytelling_direct"
    TEXT_RECEIVED = "storytelling_text_received"
    VOICE_RECEIVED = "storytelling_voice_received"
    VOICE_FAILED = "storytelling_voice_failed"
    EXTRACTED = "storytelling_extracted"
    EMPTY_RESULT = "storytelling_empty_result"
    LLM_FAILED = "storytelling_llm_failed"
    TIMED_OUT = "storytelling_timed_out"
    CANCELED = "storytelling_canceled"
    CONFIRMED_ALL = "storytelling_confirmed_all"
    DISCARDED = "storytelling_discarded"
    EDIT_REQUESTED = "storytelling_edit_requested"


# ---------- Public API ------------------------------------------------


async def start_storytelling(
    db: AsyncSession,
    chat_id: int,
    user: User,
    *,
    source: str = SOURCE_DIRECT_COMMAND,
) -> None:
    """Open storytelling mode for a user.

    Sets the wizard state and sends the welcoming prompt. Idempotent —
    calling it again resets the started_at timestamp so a user who
    re-taps "Kể chuyện" gets a fresh 10-minute window.
    """
    threshold = int(user.expense_threshold_micro or 200_000)

    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_STORYTELLING,
        step=STEP_AWAITING_STORY,
        draft={
            "started_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "threshold": threshold,
        },
    )

    threshold_short = format_money_short(threshold)
    text = (
        "💬 <b>Kể mình nghe</b>\n\n"
        "Hôm qua bạn có chi gì đáng kể không?\n"
        f"(Chi dưới <b>{threshold_short}</b> mình tự lo, không cần kể.)\n\n"
        "Ví dụ:\n"
        "• <i>Tối qua ăn nhà hàng với bạn 800k</i>\n"
        "• <i>Mua điện thoại 15tr</i>\n"
        "• <i>Đi du lịch Đà Lạt hết 5tr</i>\n\n"
        "Gõ tin nhắn hoặc gửi <b>voice</b> — cái nào tiện 🎤"
    )
    await send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    # Per-source funnel events — keep both a generic OPENED + a
    # source-specific one so dashboards can pick whichever frame they
    # need without re-deriving from properties.
    analytics.track(StorytellingEvent.OPENED, user_id=user.id,
                    properties={"source": source})
    if source == SOURCE_FROM_BRIEFING:
        analytics.track(StorytellingEvent.OPENED_FROM_BRIEFING, user_id=user.id)
    else:
        analytics.track(StorytellingEvent.OPENED_DIRECT, user_id=user.id)


async def handle_storytelling_command(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """``/story`` or ``/kechuyen`` — direct entry point."""
    await start_storytelling(db, chat_id, user, source=SOURCE_DIRECT_COMMAND)


async def is_in_storytelling_mode(user: User) -> bool:
    """True if ``user.wizard_state`` says we're mid-storytelling."""
    state = user.wizard_state or {}
    return state.get("flow") == FLOW_STORYTELLING


async def handle_storytelling_input(
    db: AsyncSession, message: dict
) -> bool:
    """Consume a text/voice message if user is in storytelling mode.

    Returns ``True`` if consumed (worker should not pass on to the NL
    expense parser), ``False`` otherwise.
    """
    chat_id = (message.get("chat") or {}).get("id")
    telegram_id = (message.get("from") or {}).get("id")
    if chat_id is None or telegram_id is None:
        return False

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None or not await is_in_storytelling_mode(user):
        return False

    state = user.wizard_state or {}
    if state.get("step") != STEP_AWAITING_STORY:
        # The confirm-pending step is driven by the inline keyboard,
        # not free-text. Anything typed during it is ignored — we
        # explicitly DON'T re-extract because the user might be answering
        # a clarification or just chatting.
        return False

    # Timeout check — if the user opened storytelling mode and walked
    # away, silently drop the mode so the next message goes to the
    # normal handlers.
    if _has_timed_out(state):
        await wizard_service.clear(db, user.id)
        analytics.track(StorytellingEvent.TIMED_OUT, user_id=user.id)
        # Don't consume — let the message fall through to NL expense
        # parser / commands.
        return False

    # Voice path
    if message.get("voice"):
        consumed = await _handle_voice_input(db, chat_id, user, message["voice"])
        return consumed

    # Text path
    text = (message.get("text") or "").strip()
    if not text:
        return False
    if text.startswith("/"):
        # Commands take priority — let them through.
        return False

    await _process_story_text(db, chat_id, user, text, source_kind="text")
    return True


async def cancel_storytelling(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Drop storytelling state and send a brief acknowledgement."""
    if not await is_in_storytelling_mode(user):
        return
    await wizard_service.clear(db, user.id)
    analytics.track(StorytellingEvent.CANCELED, user_id=user.id)
    await send_message(chat_id=chat_id, text="❌ Đã thoát chế độ kể chuyện.")


# ---------- Internal --------------------------------------------------


def _has_timed_out(state: dict) -> bool:
    started_at = (state.get("draft") or {}).get("started_at")
    if not started_at:
        return False
    try:
        ts = datetime.fromisoformat(started_at)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts) > STORYTELLING_TIMEOUT


async def _handle_voice_input(
    db: AsyncSession, chat_id: int, user: User, voice: dict,
) -> bool:
    """Download → Whisper → echo transcript → run text path."""
    duration = voice.get("duration") or 0
    if duration > MAX_VOICE_DURATION_SECONDS:
        await send_message(
            chat_id=chat_id,
            text=(
                "🎤 Voice hơi dài quá rồi 😅\n"
                "Bạn thử lại với clip ngắn hơn 60 giây nhé."
            ),
        )
        analytics.track(
            StorytellingEvent.VOICE_FAILED, user_id=user.id,
            properties={"reason": "too_long"},
        )
        return True

    file_id = voice.get("file_id")
    if not file_id:
        analytics.track(
            StorytellingEvent.VOICE_FAILED, user_id=user.id,
            properties={"reason": "missing_file_id"},
        )
        return False

    processing_msg = await send_message(
        chat_id=chat_id, text="🎤 Đang nghe bạn...",
    )

    audio_bytes = await download_file(file_id)
    if not audio_bytes:
        await send_message(
            chat_id=chat_id,
            text="Mình không tải được voice 😔 Thử lại hoặc gõ text nhé?",
        )
        analytics.track(
            StorytellingEvent.VOICE_FAILED, user_id=user.id,
            properties={"reason": "download_failed"},
        )
        return True

    try:
        transcript = await transcribe_vietnamese(audio_bytes, filename="voice.ogg")
    except VoiceTranscriptionError as exc:
        logger.warning("storytelling: voice transcription failed: %s", exc)
        await send_message(
            chat_id=chat_id,
            text=(
                "Mình chưa nghe được rõ 😔\n"
                "Bạn thử gõ text nhé — mình hiểu cả cách viết tự nhiên."
            ),
        )
        analytics.track(
            StorytellingEvent.VOICE_FAILED, user_id=user.id,
            properties={"reason": "whisper_failed"},
        )
        return True

    analytics.track(
        StorytellingEvent.VOICE_RECEIVED, user_id=user.id,
        properties={"duration_s": int(duration)},
    )

    # Edit the "đang nghe" placeholder if we got the message_id back so
    # the user sees a single threaded acknowledgement instead of two
    # separate messages — falls back to a fresh send when the edit
    # would be clumsy (no message_id, edit failed, etc.)
    transcript_msg = f"🎤 Mình nghe: <i>{_escape_html(transcript)}</i>"
    edited = False
    msg_id = _extract_message_id(processing_msg)
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
            logger.debug(
                "storytelling: edit transcript message failed", exc_info=True,
            )
    if not edited:
        await send_message(
            chat_id=chat_id, text=transcript_msg, parse_mode="HTML",
        )

    await _process_story_text(db, chat_id, user, transcript, source_kind="voice")
    return True


async def _process_story_text(
    db: AsyncSession,
    chat_id: int,
    user: User,
    story: str,
    *,
    source_kind: str,
) -> None:
    """Extract transactions and either show confirmation or empty notice."""
    if source_kind == "text":
        analytics.track(StorytellingEvent.TEXT_RECEIVED, user_id=user.id)

    state = user.wizard_state or {}
    draft = state.get("draft") or {}
    threshold = int(draft.get("threshold") or user.expense_threshold_micro or 200_000)

    processing = await send_message(
        chat_id=chat_id, text="🔍 Đang tìm giao dịch...",
    )
    proc_msg_id = _extract_message_id(processing)

    result = await extract_transactions_from_story(
        story, threshold=threshold, db=db, user_id=user.id,
    )

    # Empty: friendly clearing message, drop mode.
    if not result.transactions:
        await wizard_service.clear(db, user.id)
        text = _format_empty_result(result, threshold)
        if proc_msg_id:
            try:
                await edit_message_text(
                    chat_id=chat_id, message_id=proc_msg_id,
                    text=text, parse_mode="HTML", reply_markup=None,
                )
            except Exception:
                await send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        else:
            await send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        analytics.track(StorytellingEvent.EMPTY_RESULT, user_id=user.id)
        return

    # Stash pending transactions in wizard_state so the confirmation
    # callback (P3A-19) can read them back.
    await wizard_service.update_step(
        db, user.id,
        step=STEP_CONFIRM_PENDING,
        draft_patch={"pending": result.transactions, "story": story[:1000]},
    )

    # Build + send confirmation message. Keyboard import is local to
    # avoid a circular import (P3A-19's keyboard module imports the
    # constants from this file).
    from backend.bot.keyboards.storytelling_keyboard import (
        storytelling_confirmation_keyboard,
    )
    body = format_pending_confirmation(result.transactions, ignored=result.ignored_small)
    keyboard = storytelling_confirmation_keyboard()

    if proc_msg_id:
        try:
            await edit_message_text(
                chat_id=chat_id, message_id=proc_msg_id,
                text=body, parse_mode="HTML", reply_markup=keyboard,
            )
        except Exception:
            await send_message(
                chat_id=chat_id, text=body, parse_mode="HTML", reply_markup=keyboard,
            )
    else:
        await send_message(
            chat_id=chat_id, text=body, parse_mode="HTML", reply_markup=keyboard,
        )

    analytics.track(
        StorytellingEvent.EXTRACTED, user_id=user.id,
        properties={
            "tx_count": len(result.transactions),
            "ignored_count": len(result.ignored_small),
            "source_kind": source_kind,
        },
    )


def _format_empty_result(result: StorytellingResult, threshold: int) -> str:
    """Pretty 'no transactions found' message."""
    threshold_short = format_money_short(threshold)
    lines = [
        f"Mình không thấy giao dịch nào vượt <b>{threshold_short}</b> 😊",
    ]
    if result.ignored_small:
        lines.append(
            f"\n({len(result.ignored_small)} khoản nhỏ đã bỏ qua — "
            "mình không track giao dịch lặt vặt.)"
        )
    if result.needs_clarification:
        lines.append(
            "\nNếu có gì lớn mà mình bỏ sót, bạn nói rõ hơn rồi gửi lại nhé."
        )
    return "\n".join(lines)


def format_pending_confirmation(
    transactions: list[dict], *, ignored: list[dict] | None = None,
) -> str:
    """Build the 'mình tìm được X giao dịch — đúng hết không?' message.

    Public so the confirmation callback (P3A-19) can re-render the same
    list when the user taps "Sửa".
    """
    lines = ["🔍 <b>Mình tìm được:</b>", ""]
    total = 0
    for i, tx in enumerate(transactions, 1):
        cat = get_category(tx.get("category", "other"))
        amount = int(tx.get("amount", 0))
        total += amount
        merchant = _escape_html(str(tx.get("merchant", "Giao dịch")))[:80]
        lines.append(
            f"{i}. {cat.emoji} <b>{merchant}</b> — {format_money_short(amount)}"
        )
    lines.append("")
    lines.append(f"<i>Tổng: {format_money_short(total)} ({len(transactions)} giao dịch)</i>")
    if ignored:
        lines.append(
            f"<i>Bỏ qua {len(ignored)} khoản nhỏ dưới threshold.</i>"
        )
    lines.append("")
    lines.append("Đúng hết không?")
    return "\n".join(lines)


def _extract_message_id(send_response: object) -> int | None:
    """Pull ``message_id`` from a Telegram sendMessage response, defensively.

    Real responses are dicts shaped like
    ``{"ok": true, "result": {"message_id": 5, ...}}``. Mocks may
    return ``None`` or non-dict objects — we only accept the real
    shape and treat anything else as "no message_id available".
    """
    if not isinstance(send_response, dict):
        return None
    if not send_response.get("ok"):
        return None
    result = send_response.get("result")
    if not isinstance(result, dict):
        return None
    msg_id = result.get("message_id")
    return msg_id if isinstance(msg_id, int) else None


def _escape_html(s: str) -> str:
    """Minimal HTML escape for Telegram parse_mode=HTML.

    Inline because importing ``html.escape`` triggers a stdlib import
    that's not worth a top-level line — and we only need three chars.
    """
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------- P3A-19 Confirmation callback ------------------------------


async def handle_storytelling_callback(
    db: AsyncSession, callback_query: dict,
) -> bool:
    """Route any ``story:*`` callback. Returns True if handled.

    Lives in this module (not its own ``story_callbacks.py``) because
    every action mutates the same ``wizard_state`` and references the
    same ``pending`` draft — splitting them would force every callback
    to re-implement the lookup boilerplate.
    """
    from backend.bot.keyboards.storytelling_keyboard import (
        CB_STORY,
        STORY_ACTION_CANCEL,
        STORY_ACTION_CONFIRM_ALL,
        STORY_ACTION_EDIT,
    )

    data: str = callback_query.get("data") or ""
    if not data.startswith(f"{CB_STORY}:"):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    telegram_id = (callback_query.get("from") or {}).get("id")

    if chat_id is None or telegram_id is None:
        await answer_callback(callback_id)
        return True

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(
            callback_id,
            text="Bạn cần /start trước nhé.",
            show_alert=True,
        )
        return True

    _, parts = parse_callback(data)
    # Expected shape: story:confirm:<action>
    if len(parts) < 2 or parts[0] != "confirm":
        await answer_callback(callback_id)
        return True
    action = parts[1]

    state = user.wizard_state or {}
    if state.get("flow") != FLOW_STORYTELLING or state.get("step") != STEP_CONFIRM_PENDING:
        # Stale tap — wizard already cleared (e.g. timeout). Acknowledge
        # silently and remove the keyboard so the user doesn't try again.
        await answer_callback(
            callback_id, text="Phiên này đã hết hạn rồi 😅",
        )
        if message_id is not None:
            try:
                await edit_message_reply_markup(
                    chat_id=chat_id, message_id=message_id, reply_markup=None,
                )
            except Exception:
                logger.debug("storytelling: clear stale keyboard failed", exc_info=True)
        return True

    pending = (state.get("draft") or {}).get("pending") or []

    await answer_callback(callback_id)

    if action == STORY_ACTION_CONFIRM_ALL:
        await _confirm_all(db, chat_id, message_id, user, pending)
        return True

    if action == STORY_ACTION_CANCEL:
        await _discard_all(db, chat_id, message_id, user)
        return True

    if action == STORY_ACTION_EDIT:
        await _edit_request(db, chat_id, message_id, user, pending)
        return True

    return True  # consumed any story:* payload


async def _confirm_all(
    db: AsyncSession,
    chat_id: int,
    message_id: int | None,
    user: User,
    pending: list[dict],
) -> None:
    """Save every pending transaction and clear the storytelling state.

    Sets ``source="storytelling"`` and ``needs_review=False`` on each
    expense so the dashboard treats them as user-verified (the LLM
    extracted, the user confirmed — no human review needed).

    Failures save what they can: a single bad row doesn't roll back
    the rest. We log the failure, surface a partial-success summary,
    and keep going. The transaction boundary is owned by the worker —
    flushing here is enough; commit happens at the end of route_update.
    """
    saved: list[dict] = []
    failed = 0
    for tx in pending:
        try:
            expense = await expense_service.create_expense(
                db, user.id,
                ExpenseCreate(
                    amount=float(tx["amount"]),
                    currency="VND",
                    merchant=str(tx.get("merchant") or "Chi tiêu")[:500],
                    category=str(tx.get("category") or "other"),
                    source="storytelling",
                    expense_date=date.today(),
                    note=str(tx.get("context") or ""),
                    needs_review=False,
                ),
            )
            saved.append({
                "id": str(expense.id),
                "amount": float(expense.amount),
                "category": expense.category,
            })
        except Exception:
            logger.exception(
                "storytelling: failed to save tx for user=%s", user.id,
            )
            failed += 1

    await wizard_service.clear(db, user.id)

    total = sum(t["amount"] for t in saved)
    text = _format_save_summary(saved_count=len(saved), total=total, failed=failed)

    await _replace_or_send(
        chat_id=chat_id, message_id=message_id, text=text,
    )

    analytics.track(
        StorytellingEvent.CONFIRMED_ALL, user_id=user.id,
        properties={
            "saved_count": len(saved),
            "failed_count": failed,
            "total_amount": int(total),
        },
    )


async def _discard_all(
    db: AsyncSession,
    chat_id: int,
    message_id: int | None,
    user: User,
) -> None:
    """User tapped "❌ Bỏ hết" — drop everything, no DB writes."""
    await wizard_service.clear(db, user.id)
    text = (
        "❌ Đã bỏ qua. Không lưu gì cả.\n\n"
        "<i>Khi nào sẵn sàng kể lại, gõ /story nhé.</i>"
    )
    await _replace_or_send(chat_id=chat_id, message_id=message_id, text=text)
    analytics.track(StorytellingEvent.DISCARDED, user_id=user.id)


async def _edit_request(
    db: AsyncSession,
    chat_id: int,
    message_id: int | None,
    user: User,
    pending: list[dict],
) -> None:
    """User tapped "✏️ Sửa".

    Phase 3A keeps this minimal: drop the pending list and ask the
    user to re-tell more precisely. A full per-item edit UI (amount /
    merchant / category) is a stretch goal — issue P3A-19 spec lists
    it but the protocol survives as long as edit triggers a re-tell
    rather than silently ignoring the tap.
    """
    await wizard_service.clear(db, user.id)
    text = (
        "✏️ Bỏ qua list hiện tại — bạn kể lại rõ hơn nhé.\n\n"
        "<i>Mẹo: nói rõ tên (ăn ở đâu/mua gì), số tiền, "
        "mình sẽ phân loại đúng hơn.</i>\n\n"
        "Gõ /story khi sẵn sàng."
    )
    await _replace_or_send(chat_id=chat_id, message_id=message_id, text=text)
    analytics.track(
        StorytellingEvent.EDIT_REQUESTED,
        user_id=user.id,
        properties={"pending_count": len(pending)},
    )


def _format_save_summary(
    *, saved_count: int, total: float, failed: int,
) -> str:
    """Warm 'Đã lưu xong!' message after save."""
    if saved_count == 0:
        return (
            "Hmm, mình chưa lưu được giao dịch nào 😔\n"
            "Bạn thử /story lại nhé, mình sẽ chú ý hơn."
        )
    lines = [
        f"✅ <b>Đã lưu {saved_count} giao dịch!</b>",
        f"Tổng: <b>{format_money_short(total)}</b>",
    ]
    if failed:
        lines.append(
            f"\n<i>(Có {failed} khoản không lưu được — mình đã ghi log để debug.)</i>"
        )
    lines.append("")
    lines.append("Cảm ơn bạn kể chuyện 💚")
    return "\n".join(lines)


async def _replace_or_send(
    *, chat_id: int, message_id: int | None, text: str,
) -> None:
    """Edit the original confirmation message in-place when possible.

    Falls back to a fresh send if the edit fails (Telegram rejects
    edits older than 48 hours — shouldn't happen here but defending
    against the corner case keeps the UX intact when it does).
    """
    if message_id is not None:
        try:
            await edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=None,
            )
            return
        except Exception:
            logger.debug("storytelling: edit confirmation message failed", exc_info=True)

    await send_message(chat_id=chat_id, text=text, parse_mode="HTML")
