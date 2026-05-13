"""Wizard state service — multi-step Telegram flows backed by ``users.wizard_state``.

Phase 0/1 keeps state on the users row (single user, no Redis yet).
Shape of the JSONB blob:

    {
        "flow": "asset_add_cash",     # or asset_add_stock / asset_add_real_estate
        "step": "amount",             # step name within the flow
        "draft": {                    # accumulated wizard answers
            "asset_type": "cash",
            "subtype": "bank_savings",
            ...
        }
    }

Service flushes only — caller (worker / router) owns transaction commit.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


async def get_state(db: AsyncSession, user_id: uuid.UUID) -> dict | None:
    user = await db.get(User, user_id)
    if user is None:
        return None
    return user.wizard_state


async def start_flow(
    db: AsyncSession,
    user_id: uuid.UUID,
    flow: str,
    step: str,
    draft: dict | None = None,
) -> dict | None:
    user = await db.get(User, user_id)
    if user is None:
        return None
    user.wizard_state = {
        "flow": flow,
        "step": step,
        "draft": dict(draft or {}),
    }
    flag_modified(user, "wizard_state")
    await db.flush()
    return user.wizard_state


async def update_step(
    db: AsyncSession,
    user_id: uuid.UUID,
    step: str,
    draft_patch: dict | None = None,
) -> dict | None:
    user = await db.get(User, user_id)
    if user is None or not user.wizard_state:
        return None
    state = dict(user.wizard_state)
    state["step"] = step
    if draft_patch:
        draft = dict(state.get("draft", {}))
        draft.update(draft_patch)
        state["draft"] = draft
    user.wizard_state = state
    flag_modified(user, "wizard_state")
    await db.flush()
    return user.wizard_state


async def clear(db: AsyncSession, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    if user is None:
        return
    user.wizard_state = None
    flag_modified(user, "wizard_state")
    await db.flush()


def get_flow(state: dict | None) -> str | None:
    if not state:
        return None
    return state.get("flow")


def get_step(state: dict | None) -> str | None:
    if not state:
        return None
    return state.get("step")


def get_draft(state: dict | None) -> dict:
    if not state:
        return {}
    return dict(state.get("draft") or {})
