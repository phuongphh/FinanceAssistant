"""Handle free-text Telegram messages — natural language expense entry."""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers.transaction import send_transaction_confirmation
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service, report_service
from backend.services.dashboard_service import get_user_by_telegram_id
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

_NOT_REGISTERED = "Bạn chưa đăng ký. Gửi /start để bắt đầu."

_ASSET_QUERY_PATTERNS = (
    "tài sản của tôi",
    "danh sách tài sản",
    "xem tài sản",
    "tài sản có gì",
    "tôi có tài sản",
    "tài sản tôi",
    "liệt kê tài sản",
    "tài sản hiện tại",
    "tôi đang có gì",
)


async def _send_report(db: AsyncSession, chat_id: int, telegram_id: int, text: str = "") -> None:
    """Ask the service for report text and deliver it to the user."""
    await send_message(chat_id, "⏳ Đang tổng hợp báo cáo...")
    result = await report_service.process_report_request(db, telegram_id, text)
    await send_message(chat_id, result)


async def handle_report_command(db: AsyncSession, message: dict) -> None:
    """Handle /report command — extracts Telegram data, delegates to service."""
    chat_id = message["chat"]["id"]
    telegram_id = (message.get("from") or {}).get("id", chat_id)
    await _send_report(db, chat_id, telegram_id)


async def handle_report_callback(db: AsyncSession, callback_query: dict) -> None:
    """Handle menu:report callback — extracts Telegram data, delegates to service."""
    chat_id = callback_query["message"]["chat"]["id"]
    telegram_id = (callback_query.get("from") or {}).get("id", chat_id)
    await _send_report(db, chat_id, telegram_id)


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

    # Fast-path: report intent — service handles all orchestration.
    if report_service.is_report_query(text):
        await _send_report(db, chat_id, telegram_id, text)
        return True

    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        await send_message(chat_id, _NOT_REGISTERED)
        return True

    # Fast-path: asset list intent.
    lower = text.lower()
    if any(pat in lower for pat in _ASSET_QUERY_PATTERNS):
        from backend.bot.handlers.asset_entry import list_assets
        await list_assets(db, chat_id, user)
        return True

    try:
        raw = await call_llm(
            _PARSE_PROMPT.format(text=text),
            task_type="parse_manual",
            db=db,
            user_id=user.id,
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
