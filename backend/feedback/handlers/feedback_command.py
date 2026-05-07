from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.feedback.models.feedback import PROMPT_STATUS_RESPONDED
from backend.feedback.services import feedback_service
from backend.feedback.services.prompt_scheduler import PromptScheduler
from backend.models.user import User
from backend.services import wizard_service
from backend.services.telegram_service import answer_callback, send_message

FLOW_FEEDBACK = "feedback"
STEP_AWAITING_TEXT = "awaiting_feedback_text"

START_MESSAGE = (
    "Bé Tiền luôn muốn lắng nghe bạn 💚\n\n"
    "Bạn cứ nhắn tự nhiên: lỗi gặp phải, điều thích/chưa thích, hoặc tính năng mong muốn."
)
CONFIRMATION_MESSAGE = (
    "✅ Đã ghi nhận! Cảm ơn bạn rất nhiều 💚\n"
    "Team Bé Tiền sẽ review trong vòng 7 ngày."
)
CANCEL_MESSAGE = "Đã huỷ gửi feedback rồi nè. Khi nào muốn góp ý, bạn gõ /feedback nhé 💚"


async def start_feedback(db: AsyncSession, chat_id: int, user: User, *, trigger: str = "passive_command") -> None:
    await wizard_service.start(
        db,
        user.id,
        flow=FLOW_FEEDBACK,
        step=STEP_AWAITING_TEXT,
        draft={"trigger": trigger},
    )
    await send_message(chat_id, START_MESSAGE, parse_mode="Markdown")


async def handle_feedback_text_input(db: AsyncSession, message: dict) -> bool:
    text = message.get("text") or ""
    chat_id = message["chat"]["id"]
    telegram_id = (message.get("from") or {}).get("id")
    if telegram_id is None:
        return False

    from backend.services.dashboard_service import get_user_by_telegram_id

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None or (user.wizard_state or {}).get("flow") != FLOW_FEEDBACK:
        return False

    if text.strip().lower() in {"/cancel", "/huy"}:
        await wizard_service.clear(db, user.id)
        await send_message(chat_id, CANCEL_MESSAGE, parse_mode="Markdown")
        return True

    trigger = (user.wizard_state or {}).get("draft", {}).get("trigger") or "passive_command"
    try:
        await feedback_service.create_feedback(db, user, text, trigger=trigger)
    except feedback_service.FeedbackValidationError as exc:
        await send_message(chat_id, str(exc), parse_mode="Markdown")
        return True

    if trigger != "passive_command":
        log = await PromptScheduler()._latest_prompt_log(db, user.id, trigger)
        if log:
            log.status = PROMPT_STATUS_RESPONDED
            log.responded_at = datetime.now(timezone.utc)

    await wizard_service.clear(db, user.id)
    await send_message(chat_id, CONFIRMATION_MESSAGE, parse_mode="Markdown")
    return True


async def handle_feedback_callback(db: AsyncSession, callback_query: dict) -> bool:
    data = callback_query.get("data") or ""
    if not data.startswith("feedback:"):
        return False
    callback_id = callback_query["id"]
    parts = data.split(":", 2)
    if len(parts) != 3:
        await answer_callback(callback_id)
        return True
    action, prompt_id = parts[1], parts[2]
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")

    from backend.services.dashboard_service import get_user_by_telegram_id

    user = await get_user_by_telegram_id(db, telegram_id) if telegram_id is not None else None
    if user is None:
        await answer_callback(callback_id, "Không tìm thấy hồ sơ người dùng.")
        return True

    if action == "skip":
        await PromptScheduler().log_skip(db, user.id, prompt_id)
        await answer_callback(callback_id, "Đã ghi nhận, để sau nhé 💚")
        return True
    if action == "cta":
        await wizard_service.start(
            db,
            user.id,
            flow=FLOW_FEEDBACK,
            step=STEP_AWAITING_TEXT,
            draft={"trigger": prompt_id},
        )
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id") or user.telegram_id
        await answer_callback(callback_id)
        await send_message(chat_id, "Bạn nhắn cảm nhận của mình ở đây nhé 💚", parse_mode="Markdown")
        return True

    await answer_callback(callback_id)
    return True
