"""Handle free-text Telegram messages — natural language expense entry."""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers.transaction import send_transaction_confirmation
from backend.models.user import User
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service
from backend.services.llm_service import call_llm
from backend.services.telegram_service import send_message, send_menu

logger = logging.getLogger(__name__)

_PARSE_PROMPT = """Parse chi tiêu từ text sau và trả về JSON:
"{text}"

Trả về JSON với format:
{{"amount": <số>, "merchant": "<tên hoặc mô tả ngắn>", "is_expense": <true|false>}}

Quy tắc:
- Nếu có số tiền và mô tả → is_expense: true
- Nếu là câu hỏi, tin nhắn thông thường, không phải chi tiêu → is_expense: false, amount: 0
- "k" hoặc "K" cuối số = × 1000: 50k = 50000, 150k = 150000
- merchant = nơi mua hoặc mô tả ngắn gọn nhất

Chỉ trả về JSON, không giải thích."""


async def _get_user(db: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(
        User.telegram_id == telegram_id,
        User.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def handle_text_message(db: AsyncSession, message: dict) -> bool:
    """Try to parse a plain-text message as an expense entry.

    Returns True if the message was handled (regardless of parse outcome),
    so the caller knows whether to fall back to another handler.
    """
    text = message.get("text", "").strip()
    if not text:
        return False

    chat_id = message["chat"]["id"]
    from_data = message.get("from") or {}
    telegram_id = from_data.get("id", chat_id)

    user = await _get_user(db, telegram_id)
    if not user:
        await send_message(chat_id, "Bạn chưa đăng ký. Gửi /start để bắt đầu.")
        return True

    try:
        raw = await call_llm(
            _PARSE_PROMPT.format(text=text),
            task_type="parse_manual",
            db=db,
            use_cache=False,
        )
        # Strip markdown code fences if present
        lines = [l for l in raw.splitlines() if not l.startswith("```")]
        parsed = json.loads("\n".join(lines))
    except Exception:
        logger.exception("LLM parse failed for text: %r", text)
        return False

    if not parsed.get("is_expense") or float(parsed.get("amount", 0)) <= 0:
        # Not an expense — show menu as fallback
        await send_menu(chat_id)
        return True

    expense_data = ExpenseCreate(
        amount=float(parsed["amount"]),
        merchant=parsed.get("merchant") or text,
        note=text,
        source="manual",
        expense_date=date.today(),
    )
    expense = await expense_service.create_expense(db, user.id, expense_data)
    await send_transaction_confirmation(db, expense)
    return True
