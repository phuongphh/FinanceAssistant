"""Telegram Bot webhook router.

Thin routing layer — all transport logic lives in telegram_service,
all menu data lives in menu_service.
"""
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.handlers import onboarding as onboarding_handlers
from backend.bot.handlers.callbacks import handle_transaction_callback
from backend.bot.handlers.message import (
    handle_report_callback,
    handle_report_command,
    handle_text_message,
)
from backend.bot.personality.onboarding_flow import OnboardingStep
from backend.config import get_settings
from backend.database import get_db
from backend.services import dashboard_service
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
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _verify_webhook_request(request)

    data = await request.json()

    # Handle commands and free-text messages.
    message = data.get("message")
    if message:
        text = message.get("text", "")
        chat_id = message["chat"]["id"]
        command = text.strip().lower()
        from_user = message.get("from") or {}
        telegram_id = from_user.get("id")

        if command == "/start":
            if telegram_id is None:
                # Shouldn't happen via Telegram, but guard anyway.
                analytics.track(
                    analytics.EventType.BOT_STARTED,
                    properties={"has_telegram_id": False, "new_user": False},
                )
                return {"ok": True}

            user, created = await dashboard_service.get_or_create_user(
                db,
                telegram_id,
                first_name=from_user.get("first_name"),
                last_name=from_user.get("last_name"),
                username=from_user.get("username"),
            )
            analytics.track(
                analytics.EventType.BOT_STARTED,
                user_id=user.id,
                properties={
                    "new_user": created,
                    "is_onboarded": user.is_onboarded,
                    "has_display_name": bool(user.display_name),
                },
            )
            # resume_or_start handles both branches:
            #   - not yet onboarded → run/resume the 5-step flow
            #   - already onboarded → warm welcome-back + menu
            await onboarding_handlers.resume_or_start(db, chat_id, user)
            return {"ok": True}

        if command in ("/menu", "menu"):
            await send_menu(chat_id)
            return {"ok": True}

        if command == "/report":
            await handle_report_command(db, message)
            return {"ok": True}

        # Plain text during the onboarding name step must be consumed
        # here — otherwise the NL expense parser would try to parse the
        # user's name as a transaction.
        if text and telegram_id is not None and not command.startswith("/"):
            user = await dashboard_service.get_user_by_telegram_id(
                db, telegram_id
            )
            if user and user.onboarding_step == int(OnboardingStep.ASKING_NAME):
                consumed = await onboarding_handlers.handle_name_input(
                    db, chat_id, user, text
                )
                if consumed:
                    return {"ok": True}

        # Natural language message → NL expense parser / report intent
        # / menu fallback (see backend/bot/handlers/message.py).
        await handle_text_message(db, message)
        return {"ok": True}

    # Handle inline keyboard callbacks
    callback_query = data.get("callback_query")
    if callback_query:
        callback_data = callback_query.get("data", "")
        chat_id = callback_query["message"]["chat"]["id"]
        callback_id = callback_query["id"]

        # Onboarding callbacks first — otherwise the menu-callback
        # handler would swallow them.
        if await onboarding_handlers.handle_onboarding_callback(db, callback_query):
            return {"ok": True}

        # Transaction callbacks (edit/delete/change category/undo) handle
        # their own answerCallbackQuery so users get richer feedback.
        if await handle_transaction_callback(db, callback_query):
            return {"ok": True}

        await answer_callback(callback_id)

        # "Báo cáo" button → generate report immediately instead of
        # showing help text.
        if callback_data == "menu:report":
            await handle_report_callback(db, callback_query)
            return {"ok": True}

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
