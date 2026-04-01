"""Telegram Bot webhook/polling router.

Handles /menu command and inline keyboard callbacks directly,
bypassing OpenClaw for interactive UI elements.
"""
import logging
import uuid
from datetime import date

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/telegram", tags=["telegram"])

MENU_TEXT = """🏦 *Finance Assistant — Menu*

Chọn tính năng bạn muốn sử dụng:"""

MENU_BUTTONS = [
    [
        {"text": "📧 Quét Gmail", "callback_data": "menu:gmail_scan"},
        {"text": "📸 OCR Hóa đơn", "callback_data": "menu:ocr_info"},
    ],
    [
        {"text": "✍️ Thêm chi tiêu", "callback_data": "menu:add_expense"},
        {"text": "📊 Báo cáo", "callback_data": "menu:report"},
    ],
    [
        {"text": "📈 Thị trường", "callback_data": "menu:market"},
        {"text": "💡 Gợi ý đầu tư", "callback_data": "menu:advice"},
    ],
    [
        {"text": "🎯 Mục tiêu", "callback_data": "menu:goals"},
        {"text": "💰 Thu nhập", "callback_data": "menu:income"},
    ],
]

CALLBACK_RESPONSES = {
    "menu:gmail_scan": "📧 *Quét hóa đơn Gmail*\n\nGửi tin nhắn: \"quét gmail\" hoặc \"scan gmail\"\n\nBot sẽ quét Gmail tìm hóa đơn từ UOB Bank, Grab, Xanh SM, Traveloka và tự động ghi nhận chi tiêu.",
    "menu:ocr_info": "📸 *Nhận diện hóa đơn*\n\nGửi ảnh hóa đơn/receipt trực tiếp vào chat.\n\nBot sẽ dùng AI Vision để trích xuất:\n• Tên merchant\n• Số tiền\n• Ngày\n• Danh mục\n\nSau đó hỏi bạn confirm trước khi lưu.",
    "menu:add_expense": "✍️ *Thêm chi tiêu*\n\nGửi theo format:\n\"thêm chi tiêu [số tiền] [mô tả]\"\n\nVí dụ:\n• \"thêm chi tiêu 150k ăn trưa\"\n• \"chi 50k grab\"\n• \"ghi lại 200k shopping\"",
    "menu:report": "📊 *Báo cáo chi tiêu*\n\nGửi:\n• \"báo cáo tháng này\"\n• \"báo cáo tháng 3\"\n• \"tổng chi tiêu\"\n\nBot sẽ tổng hợp chi tiêu theo danh mục, so sánh với tháng trước, và đưa ra nhận xét.",
    "menu:market": "📈 *Thông tin thị trường*\n\nGửi:\n• \"thị trường hôm nay?\"\n• \"VN-Index?\"\n\nBot hiển thị VN-Index, VN30, HNX và các quỹ đầu tư (DCDS, VESAF...).",
    "menu:advice": "💡 *Gợi ý đầu tư*\n\nGửi: \"nên đầu tư gì?\"\n\nBot phân tích tình hình tài chính cá nhân + thị trường để đưa ra gợi ý phù hợp.",
    "menu:goals": "🎯 *Mục tiêu tài chính*\n\nGửi:\n• \"tôi muốn tiết kiệm 50tr để mua xe trong 6 tháng\"\n• \"tiến độ mục tiêu?\"\n• \"cập nhật mục tiêu\"\n\nBot theo dõi tiến độ và nhắc nhở bạn.",
    "menu:income": "💰 *Cập nhật thu nhập*\n\nGửi: \"thu nhập tháng này là 20tr\"\n\nBot dùng thu nhập để tính tỷ lệ tiết kiệm và đưa ra báo cáo chính xác hơn.",
}


async def _send_telegram(method: str, payload: dict) -> dict | None:
    """Send request to Telegram Bot API."""
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured")
        return None

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        logger.error("Telegram API error: %s %s", resp.status_code, resp.text)
        return None


async def send_menu(chat_id: int) -> dict | None:
    """Send the menu with inline keyboard to a Telegram chat."""
    return await _send_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": MENU_TEXT,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": MENU_BUTTONS},
    })


async def _get_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id, User.deleted_at.is_(None))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Telegram webhook updates."""
    data = await request.json()

    # Handle /menu command
    message = data.get("message")
    if message:
        text = message.get("text", "")
        chat_id = message["chat"]["id"]

        if text.strip().lower() in ("/menu", "/start", "menu"):
            await send_menu(chat_id)
            return {"ok": True}

    # Handle callback queries (inline keyboard button presses)
    callback_query = data.get("callback_query")
    if callback_query:
        callback_data = callback_query.get("data", "")
        chat_id = callback_query["message"]["chat"]["id"]
        callback_id = callback_query["id"]

        # Acknowledge the callback
        await _send_telegram("answerCallbackQuery", {"callback_query_id": callback_id})

        # Send feature info
        response_text = CALLBACK_RESPONSES.get(callback_data)
        if response_text:
            await _send_telegram("sendMessage", {
                "chat_id": chat_id,
                "text": response_text,
                "parse_mode": "Markdown",
            })

        return {"ok": True}

    return {"ok": True}


@router.post("/send-menu")
async def trigger_send_menu(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger sending the menu to a specific chat."""
    result = await send_menu(chat_id)
    if result:
        return {"data": {"sent": True}, "error": None}
    return {"data": None, "error": {"code": "SEND_FAILED", "message": "Failed to send menu"}}


@router.post("/set-commands")
async def set_bot_commands():
    """Register bot commands with Telegram (shown in command menu)."""
    commands = [
        {"command": "menu", "description": "Hiển thị menu tính năng"},
        {"command": "start", "description": "Bắt đầu sử dụng bot"},
        {"command": "report", "description": "Báo cáo chi tiêu tháng này"},
        {"command": "goals", "description": "Xem mục tiêu tài chính"},
        {"command": "market", "description": "Thông tin thị trường"},
    ]
    result = await _send_telegram("setMyCommands", {"commands": commands})
    if result:
        return {"data": {"registered": True}, "error": None}
    return {"data": None, "error": {"code": "REGISTER_FAILED", "message": "Failed to register commands"}}
