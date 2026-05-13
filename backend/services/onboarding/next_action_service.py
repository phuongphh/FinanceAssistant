"""Next Best Action service (Phase 4.2 Epic 2).

Computes a tiny, deterministic CTA from current user state. No LLM, no writes
inside ``compute``; handlers own persistence/side effects.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.onboarding_session import (
    GOAL_UNDERSTAND_WEALTH,
    OnboardingSession,
)
from backend.wealth.models.asset import Asset
from backend.wealth.models.income_stream import IncomeStream

_CONTENT_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "onboarding" / "next_action.yaml"
)

ASSET_STATE_DEMO = "demo"
ASSET_STATE_REAL_NO_INCOME = "real_no_income"
ASSET_STATE_REAL_WITH_INCOME = "real_with_income"
ACTION_ASKED_QUERY = "asked_query"


@dataclass(frozen=True)
class NextActionCTA:
    asset_state: str
    goal: str
    text: str
    button_key: str
    button_label: str
    callback_data: str
    action_type: str
    prefix: str
    soft_prompt: str

    @property
    def message_text(self) -> str:
        return f"{self.prefix}\n\n{self.text}\n\n💬 {self.soft_prompt}"

    @property
    def reply_markup(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [{"text": self.button_label, "callback_data": self.callback_data}]
            ]
        }


def load_copy() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


async def _has_real_asset(db: AsyncSession, user_id: uuid.UUID) -> bool:
    stmt = (
        select(Asset.id)
        .where(
            Asset.user_id == user_id,
            Asset.is_active.is_(True),
            Asset.is_placeholder_asset.is_(False),
            Asset.is_confirmed.is_(True),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).first() is not None


async def _has_income(db: AsyncSession, user_id: uuid.UUID) -> bool:
    stmt = (
        select(IncomeStream.id)
        .where(
            IncomeStream.user_id == user_id,
            IncomeStream.is_active.is_(True),
            IncomeStream.end_date.is_(None),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).first() is not None


async def asset_state(db: AsyncSession, user_id: uuid.UUID) -> str:
    if not await _has_real_asset(db, user_id):
        return ASSET_STATE_DEMO
    if await _has_income(db, user_id):
        return ASSET_STATE_REAL_WITH_INCOME
    return ASSET_STATE_REAL_NO_INCOME


async def compute(db: AsyncSession, user_id: uuid.UUID) -> NextActionCTA:
    """Return one CTA for the user's current state.

    The matrix is intentionally loaded from YAML on each call so copy can be
    tuned during soft launch without process restart.
    """
    copy = load_copy()
    session = await db.get(OnboardingSession, user_id)
    goal = (
        session.goal_choice
        if session and session.goal_choice
        else GOAL_UNDERSTAND_WEALTH
    )
    state = await asset_state(db, user_id)
    matrix_row = copy["matrix"].get(state) or copy["matrix"][ASSET_STATE_DEMO]
    cell = matrix_row.get(goal) or matrix_row[GOAL_UNDERSTAND_WEALTH]
    button_key = cell["button"]
    button = copy["buttons"][button_key]
    return NextActionCTA(
        asset_state=state,
        goal=goal,
        text=cell["text"],
        button_key=button_key,
        button_label=button["label"],
        callback_data=button["callback"],
        action_type=button["action_type"],
        prefix=copy["prefix"],
        soft_prompt=copy["soft_prompt"],
    )


def action_type_for_callback(callback_data: str) -> str | None:
    """Return the metric action type configured for a shortcut callback."""
    buttons = load_copy().get("buttons", {})
    for button in buttons.values():
        if button.get("callback") == callback_data:
            return button.get("action_type")
    return None


async def mark_taken(db: AsyncSession, user_id: uuid.UUID, action_type: str) -> None:
    session = await db.get(OnboardingSession, user_id)
    if session is None or session.next_best_action_taken is not None:
        return
    session.next_best_action_taken = action_type
    session.next_best_action_at = datetime.now(timezone.utc)
    await db.flush()
