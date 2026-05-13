"""Zalo Official Account webhook router.

Phase 4B Epic 4 (Story P4B-S23).

Single endpoint: ``POST /api/v1/zalo/webhook``. Zalo OA posts message
events here; we treat the only relevant event (``user_send_text``) as
a potential redemption attempt.

Security:
- HMAC-SHA256 signature verification against ``ZALO_OA_SECRET_KEY``
  using the ``X-ZEvent-Signature`` header. If a request fails
  verification we return 403 and log the failure — never leak which
  user_id was targeted.
- Signature check is skipped only when the secret is empty (dev
  bypass), matching the Telegram webhook's pattern.

Layer contract:
- Router parses the request, runs auth, dispatches to the service,
  and commits ONCE at the boundary.
- Business logic (token lookup, user binding) lives in
  :mod:`backend.services.zalo_linking_service`.
- Zalo confirmation reply goes through :class:`ZaloNotifier`, NOT
  the OA client directly, so it goes through the same plain-text /
  truncation guards as the alert path.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.zalo_notifier import ZaloNotifier
from backend.adapters.zalo_oa import get_zalo_oa_client
from backend.config import get_settings
from backend.database import get_db
from backend.services import zalo_linking_service
from backend.services.telegram_service import send_message
from backend.models.user import User
from sqlalchemy import select

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/zalo", tags=["zalo"])

_ZALO_CONTENT_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "zalo.yaml"
)


@lru_cache(maxsize=1)
def _load_copy() -> dict[str, Any]:
    with open(_ZALO_CONTENT_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _linking_copy(key: str) -> str:
    return (_load_copy().get("linking") or {}).get(key, "")


def _verify_zalo_signature(body: bytes, signature_header: str | None) -> bool:
    """Verify the Zalo HMAC-SHA256 signature.

    Zalo signs each webhook payload with the OA secret key and posts
    the hex digest in ``X-ZEvent-Signature``. The header format is
    ``"sha256=<hex>"``; some Zalo SDK versions send only the hex.
    We accept both.

    When ``ZALO_OA_SECRET_KEY`` is empty, signature verification is
    skipped (dev-only bypass).
    """
    if not settings.zalo_oa_secret_key:
        return True  # dev mode — no secret configured
    if not signature_header:
        return False

    received = signature_header.strip()
    if received.startswith("sha256="):
        received = received[len("sha256=") :]

    expected = hmac.new(
        settings.zalo_oa_secret_key.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(received.lower(), expected.lower())


@router.post("/webhook")
async def zalo_webhook(
    request: Request,
    x_zevent_signature: str | None = Header(default=None, alias="X-ZEvent-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle inbound Zalo OA events.

    Returns 200 with ``{"ok": True}`` for all valid events even if
    the message wasn't a redemption — Zalo retries on non-200 and we
    don't want them retrying a user "hi" message indefinitely.
    """
    body = await request.body()
    if not _verify_zalo_signature(body, x_zevent_signature):
        logger.warning("Zalo webhook signature mismatch — rejecting")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid signature",
        )

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Zalo webhook: malformed JSON body")
        return {"ok": True}

    event_name = payload.get("event_name", "")
    sender = payload.get("sender") or {}
    zalo_user_id = sender.get("id")
    message = (payload.get("message") or {}).get("text", "")

    # We only act on inbound user text. Other events (follow, unfollow,
    # delivery receipts) are logged for analytics but produce no reply.
    if event_name not in {"user_send_text", "user_send_message"}:
        return {"ok": True}
    if not zalo_user_id or not message:
        return {"ok": True}

    await _handle_inbound_text(db, zalo_user_id=str(zalo_user_id), text=message)
    await db.commit()
    return {"ok": True}


async def _handle_inbound_text(
    db: AsyncSession, *, zalo_user_id: str, text: str
) -> None:
    """Process one inbound Zalo text message.

    Branches:
    1. Message contains a ``BT-XXXXXX`` token → attempt redemption.
       - Success: confirm via Zalo (and Telegram if user was newly linked).
       - Invalid/expired/used: tell the user via Zalo with a helpful nudge.
    2. Already-linked user sends arbitrary text → respond with a brief
       "you're linked, alerts will come here" so they know they reached us.
    3. Unknown sender + no token → reply with the linking instructions
       brief so they understand how to use the OA.
    """
    notifier = ZaloNotifier(client=get_zalo_oa_client(), zalo_user_id=zalo_user_id)
    token = zalo_linking_service.normalize_token_input(text)

    if token:
        result = await zalo_linking_service.redeem_link_token(
            db, token=token, zalo_user_id=zalo_user_id
        )
        if result.status in ("linked", "user_relinked"):
            # Confirm on both channels per Story #440 acceptance criteria.
            await notifier.send_message(0, _linking_copy("confirm_zalo"))
            await _notify_telegram_user(db, user_id=result.user_id)
            return
        if result.status == "already_used":
            await notifier.send_message(0, _linking_copy("token_already_used"))
            return
        if result.status == "expired":
            await notifier.send_message(0, _linking_copy("token_expired"))
            return
        # status == "invalid" or unknown
        await notifier.send_message(0, _linking_copy("token_invalid"))
        return

    # Non-token text — short helpful response.
    existing = (
        await db.execute(
            select(User).where(User.zalo_user_id == zalo_user_id)
        )
    ).scalar_one_or_none()
    if existing:
        await notifier.send_message(0, _linking_copy("confirm_zalo"))
    else:
        await notifier.send_message(0, _linking_copy("token_invalid"))


async def _notify_telegram_user(
    db: AsyncSession, *, user_id: Any
) -> None:
    """Send the linking-success confirmation back to Telegram."""
    if user_id is None:
        return
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        return
    await send_message(
        chat_id=user.telegram_id,
        text=_linking_copy("confirm_telegram"),
    )
