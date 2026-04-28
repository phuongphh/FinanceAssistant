"""Telegram Bot webhook router.

Thin routing layer — verifies the request, atomically claims the
``update_id`` (see ``telegram_updates`` table for the dedup + orphan
recovery design), then hands processing off to a background task so the
webhook returns 200 in ≤100ms regardless of downstream LLM latency.

All dispatch logic lives in ``backend/workers/telegram_worker.py``.
See docs/archive/scaling-refactor-A.md §A1 and §A3.
"""
import asyncio
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.models.telegram_update import TelegramUpdate
from backend.services.menu_service import get_features_json, get_menu_text
from backend.services.telegram_service import register_bot_commands, send_menu
from backend.workers.telegram_worker import process_update_safely

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


async def _claim_update(
    db: AsyncSession, update_id: int, payload: dict
) -> bool:
    """Atomically record the update_id. Returns True if we claimed it
    (first time seen), False if it was already present (Telegram retry).

    Uses Postgres ``INSERT ... ON CONFLICT DO NOTHING`` so the check is
    one round trip and race-free even across uvicorn workers.
    """
    stmt = (
        pg_insert(TelegramUpdate)
        .values(update_id=update_id, payload=payload)
        .on_conflict_do_nothing(index_elements=["update_id"])
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount == 1


def _enqueue_update(update_id: int, data: dict) -> None:
    """Thin wrapper around asyncio.create_task so tests can patch this
    function rather than asyncio.create_task (which is shared with anyio
    internals and causes failures under Python 3.13 when patched globally).
    """
    asyncio.create_task(process_update_safely(update_id, data))


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _verify_webhook_request(request)

    data = await request.json()
    update_id = data.get("update_id")
    if update_id is None:
        # Malformed update — ack so Telegram stops retrying, but do nothing.
        logger.warning("Telegram update missing update_id; body keys=%s", list(data.keys()))
        return {"ok": True}

    claimed = await _claim_update(db, update_id, data)
    if not claimed:
        logger.info("Duplicate Telegram update_id=%s — skipping", update_id)
        return {"ok": True}

    # Fire-and-forget. The task opens its own session, routes the update,
    # and marks the telegram_updates row as done/failed. A crash here
    # leaves the row in 'processing' which the startup hook picks up.
    _enqueue_update(update_id, data)
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
