"""Telegram Bot webhook/polling router.

Handles /menu command and inline keyboard callbacks.
All menu data comes from menu_service (single source of truth).
"""
import logging

import httpx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.services.menu_service import (
    BOT_COMMANDS,
    get_callback_response,
    get_features_json,
    get_menu_text,
    get_telegram_buttons,
    get_telegram_menu_text,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/telegram", tags=["telegram"])


async def _send_telegram(method: str, payload: dict) -> dict | None:
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
    return await _send_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": get_telegram_menu_text(),
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": get_telegram_buttons()},
    })


@router.post("/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()

    message = data.get("message")
    if message:
        text = message.get("text", "")
        chat_id = message["chat"]["id"]

        if text.strip().lower() in ("/menu", "/start", "menu"):
            await send_menu(chat_id)
            return {"ok": True}

    callback_query = data.get("callback_query")
    if callback_query:
        callback_data = callback_query.get("data", "")
        chat_id = callback_query["message"]["chat"]["id"]
        callback_id = callback_query["id"]

        await _send_telegram("answerCallbackQuery", {"callback_query_id": callback_id})

        response_text = get_callback_response(callback_data)
        if response_text:
            await _send_telegram("sendMessage", {
                "chat_id": chat_id,
                "text": response_text,
                "parse_mode": "Markdown",
            })

        return {"ok": True}

    return {"ok": True}


@router.get("/menu")
async def get_menu():
    """Return menu data as JSON — consumed by OpenClaw skills and other clients."""
    return {
        "data": {
            "text": get_menu_text(),
            "features": get_features_json(),
        },
        "error": None,
    }


@router.post("/send-menu")
async def trigger_send_menu(chat_id: int = Query(...)):
    result = await send_menu(chat_id)
    if result:
        return {"data": {"sent": True}, "error": None}
    return {"data": None, "error": {"code": "SEND_FAILED", "message": "Failed to send menu"}}


@router.post("/set-commands")
async def set_bot_commands():
    result = await _send_telegram("setMyCommands", {"commands": BOT_COMMANDS})
    if result:
        return {"data": {"registered": True}, "error": None}
    return {"data": None, "error": {"code": "REGISTER_FAILED", "message": "Failed to register commands"}}
