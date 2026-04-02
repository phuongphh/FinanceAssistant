"""Telegram Bot webhook router.

Thin routing layer — all transport logic lives in telegram_service,
all menu data lives in menu_service.
"""
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.services.menu_service import get_features_json, get_menu_text
from backend.services.telegram_service import (
    answer_callback,
    handle_menu_callback,
    register_bot_commands,
    send_menu,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _verify_webhook_request(request: Request) -> None:
    """Validate that the webhook request comes from Telegram.

    Uses the X-Telegram-Bot-Api-Secret-Token header, which Telegram sends
    when a secret_token is configured via setWebhook.
    """
    if not settings.telegram_webhook_secret:
        return  # Skip validation if secret not configured (dev mode)

    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(token, settings.telegram_webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook token")


@router.post("/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    _verify_webhook_request(request)

    data = await request.json()

    # Handle /menu command
    message = data.get("message")
    if message:
        text = message.get("text", "")
        chat_id = message["chat"]["id"]

        if text.strip().lower() in ("/menu", "/start", "menu"):
            await send_menu(chat_id)
            return {"ok": True}

    # Handle inline keyboard callbacks
    callback_query = data.get("callback_query")
    if callback_query:
        callback_data = callback_query.get("data", "")
        chat_id = callback_query["message"]["chat"]["id"]
        callback_id = callback_query["id"]

        await answer_callback(callback_id)
        await handle_menu_callback(chat_id, callback_data)
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
    result = await register_bot_commands()
    if result:
        return {"data": {"registered": True}, "error": None}
    return {"data": None, "error": {"code": "REGISTER_FAILED", "message": "Failed to register commands"}}
