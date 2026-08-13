"""Telegram side of the Zalo → Telegram invite — Phase 5.0 #1028.

Zalo onboarding ends by offering a Telegram link. That link used to be a
bare bot URL, so the tap arrived at ``/start`` as an anonymous newcomer
and Telegram minted a *second* ``User`` row: one person, two accounts,
each holding half a financial history, with nothing on either side
pointing at the other.

The invite now carries a single-use adoption token in the ``/start``
deep-link payload. This module spends it *before* ``get_or_create_user``
runs, writing ``telegram_id`` onto the Zalo row that already exists.

Layer contract: this is a handler — it routes, formats and sends. The
binding itself lives in ``zalo_linking_service``; the worker commits.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.models.user import User
from backend.services import dashboard_service, zalo_linking_service
from backend.services.onboarding import onboarding_service
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

# Namespace for the ``/start`` payload. ``onboarding_v2`` already routes
# on ``invite_`` and ``src_`` prefixes; an unprefixed token would fall
# into its catch-all branch and be silently read as a source name.
ADOPT_PAYLOAD_PREFIX = "zalo_"


def adoption_token(payload: str | None) -> str | None:
    """Extract the adoption token from a ``/start`` payload, if it is one."""
    if not payload or not payload.startswith(ADOPT_PAYLOAD_PREFIX):
        return None
    token = payload[len(ADOPT_PAYLOAD_PREFIX) :].strip()
    return token or None


def build_payload(token: str) -> str:
    """Wrap a token into the ``/start`` payload the invite link carries."""
    return f"{ADOPT_PAYLOAD_PREFIX}{token}"


async def try_adopt(
    db: AsyncSession,
    chat_id: int,
    *,
    payload: str | None,
    telegram_id: int,
    from_user: dict[str, Any] | None = None,
) -> User | None:
    """Redeem an adoption payload. Returns the adopted user, else ``None``.

    ``None`` means "not an adoption" — an ordinary ``/start``, or a token
    that cannot be honoured — and the caller should continue with its
    normal new-user path. Refusing rather than forcing a binding is
    deliberate: ``already_used`` and ``conflict`` both mean some *other*
    account is already involved, and re-pointing a ``telegram_id`` would
    hand one person's data to another.
    """
    token = adoption_token(payload)
    if token is None:
        return None

    from_user = from_user or {}
    result = await zalo_linking_service.adopt_telegram_account(
        db,
        token,
        telegram_id,
        telegram_handle=from_user.get("username"),
        display_name=from_user.get("first_name") or from_user.get("last_name"),
    )
    if result.status != "adopted" or result.user is None:
        logger.warning(
            "Zalo adoption refused (status=%s) for telegram_id=%s", result.status, telegram_id
        )
        analytics.track(
            "zalo_telegram_adopt_failed", properties={"status": result.status}
        )
        return None

    user = result.user
    # The suspension check ran before us and cached ``None`` for this
    # telegram_id. Left alone, the caller's ``get_or_create_user`` would
    # trust that cached miss and create the duplicate we just prevented.
    dashboard_service.remember_user(db, user)

    await _greet(chat_id, user)
    analytics.track("zalo_telegram_adopted", user_id=user.id)
    logger.info("Adopted Telegram %s onto Zalo-first user %s", telegram_id, user.id)
    return user


async def _greet(chat_id: int, user: User) -> None:
    """Send the "your account came with you" message, if copy exists."""
    block = onboarding_service.load_copy().get("zalo_adopt") or {}
    template = str(block.get("greeting") or "").strip()
    if not template:
        logger.warning("Zalo adoption: greeting copy missing")
        return
    text = template.format(salutation=onboarding_service.salutation_of(user))
    await send_message(chat_id, text, parse_mode="HTML")
