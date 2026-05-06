"""/about command handler.

Keeps product trust metadata in one fast, dependency-light place so the
command can answer immediately without touching the database.
"""
from __future__ import annotations

from backend.config import APP_VERSION
from backend.services.telegram_service import send_message

ABOUT_TEXT = f"""💎 *Bé Tiền — Personal CFO*
_Trợ lý CFO cá nhân đầu tiên dành cho người Việt_

📦 *Phiên bản:* {APP_VERSION}
🏢 *Phát triển bởi:* Nui Truc AI

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
        [{"text": "📧 Hỗ Trợ", "url": "mailto:admin@nuitruc.ai"}],
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
