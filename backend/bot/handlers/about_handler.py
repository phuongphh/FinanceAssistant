"""/about command handler.

Keeps product trust metadata in one fast, dependency-light place so the
command can answer immediately without touching the database.
"""
from __future__ import annotations

from backend.config import APP_VERSION
from backend.services.telegram_service import answer_callback, send_message

ABOUT_SUPPORT_EMAIL = "admin@nuitruc.ai"
ABOUT_SUPPORT_CALLBACK = "about:support"
ABOUT_SUPPORT_ALERT = f"📧 Hỗ trợ: {ABOUT_SUPPORT_EMAIL}"

ABOUT_TEXT = f"""💎 *Bé Tiền*
_Trợ lý quản lý Tài sản cá nhân đầu tiên dành cho người Việt_

📦 *Phiên bản:* {APP_VERSION}
🏢 *Phát triển bởi:* Nui Truc AI
📧 *Hỗ trợ:* {ABOUT_SUPPORT_EMAIL}

━━━━━━━━━━━━━━━
🔒 *Bảo mật dữ liệu*
Dữ liệu tài chính của bạn được mã hóa và lưu trữ an toàn.
Chúng tôi không bao giờ chia sẻ thông tin cá nhân với bên thứ ba.
━━━━━━━━━━━━━━━

© 2026 Nui Truc AI. All rights reserved."""

ABOUT_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "🌐 Website Công Ty", "url": "https://nuitruc.ai"}],
        [{"text": "🔏 Chính Sách Bảo Mật", "url": "https://nuitruc.ai/privacy"}],
        [{"text": "📧 Hỗ Trợ", "callback_data": ABOUT_SUPPORT_CALLBACK}],
    ]
}


async def cmd_about(chat_id: int) -> None:
    """Send the product About page for ``/about``."""
    await send_message(
        chat_id=chat_id,
        text=ABOUT_TEXT,
        parse_mode="Markdown",
        reply_markup=ABOUT_KEYBOARD,
    )


async def handle_about_callback(callback_query: dict) -> bool:
    """Handle callbacks from the About page inline keyboard."""
    if callback_query.get("data") != ABOUT_SUPPORT_CALLBACK:
        return False

    await answer_callback(
        callback_query["id"],
        text=ABOUT_SUPPORT_ALERT,
        show_alert=True,
    )
    return True
