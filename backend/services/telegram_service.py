"""Telegram Bot API transport layer.

All Telegram API interactions go through this service.
Routers should never call Telegram API directly.
"""
import logging

import httpx

from backend.config import get_settings
from backend.services.menu_service import (
    BOT_COMMANDS,
    get_callback_response,
    get_telegram_buttons,
    get_telegram_menu_text,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_telegram(method: str, payload: dict) -> dict | None:
    """Send a request to the Telegram Bot API."""
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


async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> dict | None:
    return await send_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    })


async def send_menu(chat_id: int) -> dict | None:
    """Send the interactive menu with inline keyboard."""
    return await send_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": get_telegram_menu_text(),
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": get_telegram_buttons()},
    })


async def answer_callback(callback_id: str) -> dict | None:
    return await send_telegram("answerCallbackQuery", {"callback_query_id": callback_id})


async def handle_menu_callback(chat_id: int, callback_data: str) -> dict | None:
    """Look up the callback response and send it."""
    response_text = get_callback_response(callback_data)
    if response_text:
        return await send_message(chat_id, response_text)
    return None


async def register_bot_commands() -> dict | None:
    return await send_telegram("setMyCommands", {"commands": BOT_COMMANDS})
