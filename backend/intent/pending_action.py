"""Pending-action / awaiting-clarification state.

Stored on ``users.wizard_state`` (JSONB) under a dedicated ``flow``
namespace so the asset-entry / storytelling wizards don't collide.
Two flow names live here:

  - ``intent_pending_action``     — user typed a write intent at
    medium confidence; we sent a confirmation. The next callback (or
    /huy) clears it.
  - ``intent_awaiting_clarify``   — user typed a low-confidence query;
    we sent a clarification prompt. The next text or callback resolves
    it.

State expires after ``CLARIFY_TTL_SECONDS`` (10 min). The dispatcher
checks ``is_expired`` before honouring a stale state — any expired row
is treated as no state (and lazily cleared on next access).

Service contract: every mutator takes ``db`` and ``user``, mutates
``user.wizard_state`` in place, and ``db.flush()``-es. The worker /
router commits per the layer contract.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User

logger = logging.getLogger(__name__)


FLOW_PENDING_ACTION = "intent_pending_action"
FLOW_AWAITING_CLARIFY = "intent_awaiting_clarify"

CLARIFY_TTL_SECONDS = 10 * 60  # 10 minutes per acceptance criteria.


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(created_at_iso: str) -> bool:
    try:
        created = datetime.fromisoformat(created_at_iso)
    except (TypeError, ValueError):
        return True
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - created).total_seconds()
    return age > CLARIFY_TTL_SECONDS


async def set_pending_action(
    db: AsyncSession,
    user: User,
    *,
    intent: str,
    parameters: dict[str, Any],
) -> None:
    """Save a write-intent confirmation in flight."""
    user.wizard_state = {
        "flow": FLOW_PENDING_ACTION,
        "created_at": _now_iso(),
        "intent": intent,
        "parameters": dict(parameters),
    }
    await db.flush()


async def set_awaiting_clarification(
    db: AsyncSession,
    user: User,
    *,
    intent: str,
    raw_text: str,
    parameters: dict[str, Any] | None = None,
) -> None:
    """Save a low-confidence query awaiting user clarification."""
    user.wizard_state = {
        "flow": FLOW_AWAITING_CLARIFY,
        "created_at": _now_iso(),
        "original_intent": intent,
        "raw_text": raw_text,
        "parameters": dict(parameters or {}),
    }
    await db.flush()


async def clear(db: AsyncSession, user: User) -> None:
    """Drop any intent state. No-op if there's nothing to clear."""
    state = user.wizard_state or {}
    if state.get("flow") in (FLOW_PENDING_ACTION, FLOW_AWAITING_CLARIFY):
        user.wizard_state = None
        await db.flush()


def get_active(user: User) -> dict[str, Any] | None:
    """Return the active intent state if not expired, else None.

    Read-only — does NOT clear expired state from the DB. Use
    ``clear_if_expired`` from a write context for that.
    """
    state = user.wizard_state or {}
    if state.get("flow") not in (FLOW_PENDING_ACTION, FLOW_AWAITING_CLARIFY):
        return None
    if _is_expired(state.get("created_at", "")):
        return None
    return state


async def clear_if_expired(db: AsyncSession, user: User) -> bool:
    """Drop expired intent state. Returns True if something was cleared."""
    state = user.wizard_state or {}
    if state.get("flow") not in (FLOW_PENDING_ACTION, FLOW_AWAITING_CLARIFY):
        return False
    if not _is_expired(state.get("created_at", "")):
        return False
    user.wizard_state = None
    await db.flush()
    return True


__all__ = [
    "CLARIFY_TTL_SECONDS",
    "FLOW_AWAITING_CLARIFY",
    "FLOW_PENDING_ACTION",
    "clear",
    "clear_if_expired",
    "get_active",
    "set_awaiting_clarification",
    "set_pending_action",
]
