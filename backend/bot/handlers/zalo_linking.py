"""Telegram handlers for the Zalo linking flow.

Phase 4B Epic 4 (Story P4B-S23).

Commands:
- ``/link_zalo``    → issue + display a single-use linking token.
- ``/unlink_zalo``  → clear ``users.zalo_user_id``.

The redemption side lives in :mod:`backend.routers.zalo` (the OA
webhook). Both sides call :mod:`backend.services.zalo_linking_service`
so business logic stays out of the transport layer.

Layer contract:
- These handlers parse Telegram data, call the service, and format
  a reply. They never read env vars directly (the service does that
  via the ``ZaloOAClient`` factory).
- The handler does NOT commit; the worker (``telegram_worker.route_update``)
  owns the transaction boundary.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.zalo_oa import get_zalo_oa_client
from backend.models.user import User
from backend.services import zalo_linking_service
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

_ZALO_CONTENT_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "zalo.yaml"
)


@lru_cache(maxsize=1)
def _load_copy() -> dict[str, Any]:
    with open(_ZALO_CONTENT_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _linking_copy(key: str) -> str:
    return (_load_copy().get("linking") or {}).get(key, "")


async def cmd_link_zalo(
    db: AsyncSession, chat_id: int, user: User | None
) -> None:
    """Handle ``/link_zalo`` — issue a token + display instructions."""
    if user is None:
        # Not onboarded — fall back to /start. We don't issue a token
        # for an anonymous Telegram user because there's nothing to bind.
        await send_message(
            chat_id,
            "Bạn cần hoàn tất /start trước khi liên kết Zalo nhé!",
        )
        return

    # Zalo OA not configured → tell the user instead of dangling a
    # token they could never redeem.
    if not get_zalo_oa_client().is_configured:
        await send_message(chat_id, _linking_copy("not_configured"))
        return

    if user.zalo_user_id:
        await send_message(chat_id, _linking_copy("already_linked"))
        return

    token = await zalo_linking_service.issue_link_token(db, user)
    text = _linking_copy("prompt").format(token=token)
    # Markdown keeps the token in a code block on Telegram so it's
    # tappable to copy on mobile.
    await send_message(chat_id, text, parse_mode="Markdown")


async def cmd_unlink_zalo(
    db: AsyncSession, chat_id: int, user: User | None
) -> None:
    """Handle ``/unlink_zalo`` — clear the Zalo binding."""
    if user is None:
        await send_message(
            chat_id,
            "Bạn cần hoàn tất /start trước khi dùng lệnh này nhé!",
        )
        return

    was_linked = await zalo_linking_service.unlink_user(db, user)
    if was_linked:
        await send_message(chat_id, _linking_copy("unlinked"))
    else:
        await send_message(chat_id, _linking_copy("not_linked"))


def profile_status_line(user: User) -> str:
    """One-line Zalo link status — embedded in the /profile view."""
    copy = _load_copy().get("profile_status", {})
    if user.zalo_user_id:
        return copy.get("linked", "🔗 Zalo: đã liên kết")
    return copy.get("not_linked", "🔗 Zalo: chưa liên kết (dùng /link_zalo)")
