"""Onboarding service — business logic for the 5-step flow.

Handlers call into this module for every state change so tests and
analytics have a single choke point. All DB writes go through here;
handlers stay focused on shaping messages.

User lookup / creation lives in `dashboard_service` (the canonical
single source of truth) — this module deliberately does not duplicate
those helpers.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.personality.onboarding_flow import OnboardingStep, PRIMARY_GOALS
from backend.models.user import User

logger = logging.getLogger(__name__)

MAX_DISPLAY_NAME_LEN = 50
MIN_DISPLAY_NAME_LEN = 1


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def set_step(
    db: AsyncSession, user_id: uuid.UUID, step: OnboardingStep
) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.onboarding_step = int(step)
    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()


async def set_display_name(
    db: AsyncSession, user_id: uuid.UUID, name: str
) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.display_name = name
    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()


async def set_primary_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_code: str
) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.primary_goal = goal_code
    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()


async def mark_completed(db: AsyncSession, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.onboarding_step = int(OnboardingStep.COMPLETED)
    user.onboarding_completed_at = datetime.now(timezone.utc)
    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()


async def mark_skipped(db: AsyncSession, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.onboarding_skipped = True
    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()


async def is_in_first_transaction_step(
    db: AsyncSession, user_id: uuid.UUID
) -> bool:
    user = await db.get(User, user_id)
    if not user:
        return False
    return user.onboarding_step == int(OnboardingStep.FIRST_TRANSACTION)


def is_valid_goal_code(goal_code: str) -> bool:
    return goal_code in PRIMARY_GOALS


def validate_display_name(raw: str) -> tuple[bool, str | None]:
    """Return (is_valid, cleaned_or_None).

    Keeps validation pure so tests don't need a DB session.
    """
    name = (raw or "").strip()
    if len(name) < MIN_DISPLAY_NAME_LEN:
        return False, None
    if len(name) > MAX_DISPLAY_NAME_LEN:
        return False, None
    return True, name
