"""Phase 3.6 bot menu commands — the key entries that show up under the
Telegram bot menu button (corner of the chat input).

These are **shortcuts**, not the rich /menu inline UI:

  /start     — onboarding entry
  /menu      — opens the rich 5-category inline menu (the real UX)
  /help      — short usage guide (handled via Phase 3.5 HELP intent)
  /dashboard  — opens the wealth Mini App in-place
  /baocaosang — resend today's morning briefing on demand
  /about      — product version, privacy and support info

The bot menu button is a Telegram-native list of slash commands — tapping
one inserts the command into the input and sends it. So each command
must have a working route somewhere in the worker; missing handlers
would silently fall through to the unclear-message branch.

Routing of these slash commands lives in ``workers/telegram_worker._handle_message``:
  - ``/start`` and ``/menu`` already had explicit branches before Epic 2
  - ``/help`` matches the rule-based pattern in ``intent_patterns.yaml``
    and resolves through the normal text path
  - ``/dashboard`` is wired in the worker as part of Epic 2
  - ``/baocaosang`` renders the enriched morning briefing on demand
  - ``/about`` is wired in the worker and renders static product info

Old Phase 3A commands (``/themtaisan``, ``/taisan``, ``/report``, ``/goals``,
``/market``) still work as text — they just no longer appear in the menu
button list. Surfacing a small set of high-leverage entry points reduces decision
friction; the rich /menu is one tap away for everything else.
"""
from __future__ import annotations

import logging

from backend.services.telegram_service import send_telegram

logger = logging.getLogger(__name__)


BOT_COMMANDS: list[dict[str, str]] = [
    {"command": "start", "description": "Bắt đầu / Onboarding"},
    {"command": "menu", "description": "Menu chính"},
    {"command": "help", "description": "Hướng dẫn sử dụng"},
    {"command": "dashboard", "description": "Mở Mini App dashboard"},
    {"command": "baocaosang", "description": "Gửi lại briefing sáng"},
    {"command": "feedback", "description": "Gửi góp ý nhanh"},
    {"command": "about", "description": "Thông tin ứng dụng"},
]


async def setup_bot_commands() -> dict | None:
    """Sync ``BOT_COMMANDS`` with Telegram via ``setMyCommands``.

    Called once on FastAPI startup (see ``backend/main.py`` lifespan).
    Returns the API response on success, ``None`` if the bot token
    isn't configured. Errors propagate so startup logs show the
    failure — the lifespan wraps this in a try/except.
    """
    return await send_telegram("setMyCommands", {"commands": BOT_COMMANDS})
