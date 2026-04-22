"""Handle free-text Telegram messages — natural language expense entry."""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers.transaction import send_transaction_confirmation
from backend.models.user import User
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service
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

# Keywords that signal the user wants a spending report, not to log an expense.
_REPORT_KEYWORDS = frozenset([
    "báo cáo", "bao cao",
    "tổng chi tiêu", "tong chi tieu",
    "chi tiêu tháng", "chi tieu thang",
    "xài bao nhiêu", "xai bao nhieu",
    "tôi xài bao", "toi xai bao",
    "tôi đã chi", "toi da chi",
    "spending", "report",
    "tháng trước tôi", "thang truoc toi",
])


def _looks_like_report_query(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _REPORT_KEYWORDS)


def _extract_month_key(text: str) -> str:
    """Best-effort month extraction from natural language. Defaults to current month."""
    today = date.today()
    lower = text.lower()

    if "tháng trước" in lower or "thang truoc" in lower:
        m = today.month - 1 or 12
        y = today.year if today.month > 1 else today.year - 1
        return f"{y}-{m:02d}"

    # "tháng 3" or "tháng 03"
    match = re.search(r"tháng\s+(\d{1,2})", lower)
    if match:
        month = int(match.group(1))
        if 1 <= month <= 12:
            year = today.year if month <= today.month else today.year - 1
            return f"{year}-{month:02d}"

    # Explicit "2026-03"
    match = re.search(r"(\d{4})-(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"

    return today.strftime("%Y-%m")


_NOT_REGISTERED = "Bạn chưa đăng ký. Gửi /start để bắt đầu."


async def handle_report_request(db: AsyncSession, chat_id: int, user: User, text: str) -> None:
    """Generate and send a monthly spending report."""
    from backend.services.report_service import generate_monthly_report

    month_key = _extract_month_key(text)
    await send_message(chat_id, "⏳ Đang tổng hợp báo cáo...")
    try:
        report = await generate_monthly_report(db, user.id, month_key)
        await send_message(chat_id, report.report_text or "Không có dữ liệu chi tiêu.")
    except Exception:
        logger.exception("Report generation failed for user %s month %s", user.id, month_key)
        await send_message(chat_id, "❌ Không thể tổng hợp báo cáo. Thử lại sau nhé.")


async def handle_report_command(db: AsyncSession, message: dict) -> None:
    """Handle /report command — router delegates here, keeping logic out of the router."""
    chat_id = message["chat"]["id"]
    from_data = message.get("from") or {}
    telegram_id = from_data.get("id", chat_id)
    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        await send_message(chat_id, _NOT_REGISTERED)
        return
    await handle_report_request(db, chat_id, user, "")


async def handle_report_callback(db: AsyncSession, callback_query: dict) -> None:
    """Handle menu:report callback — router delegates here, keeping logic out of the router."""
    chat_id = callback_query["message"]["chat"]["id"]
    from_data = callback_query.get("from") or {}
    telegram_id = from_data.get("id", chat_id)
    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        await send_message(chat_id, _NOT_REGISTERED)
        return
    await handle_report_request(db, chat_id, user, "")


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

    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        await send_message(chat_id, _NOT_REGISTERED)
        return True

    # Fast-path: report intent detected without an LLM call.
    if _looks_like_report_query(text):
        await handle_report_request(db, chat_id, user, text)
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
