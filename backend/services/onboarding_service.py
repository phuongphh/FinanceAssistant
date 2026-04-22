"""Onboarding service — business logic for the 5-step flow.

Handlers call into this module for every state change so tests and
analytics have a single choke point. All DB writes go through here;
handlers stay focused on shaping messages.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.personality.onboarding_flow import OnboardingStep, PRIMARY_GOALS
from backend.models.user import User

logger = logging.getLogger(__name__)

MAX_DISPLAY_NAME_LEN = 50
MIN_DISPLAY_NAME_LEN = 1


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_telegram_id(
    db: AsyncSession, telegram_id: int
) -> User | None:
    stmt = select(User).where(
        User.telegram_id == telegram_id,
        User.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_or_create_user(
    db: AsyncSession,
    telegram_id: int,
    telegram_handle: str | None = None,
) -> tuple[User, bool]:
    """Return (user, created). Creates a row if telegram_id is new."""
    user = await get_user_by_telegram_id(db, telegram_id)
    if user:
        return user, False

    user = User(
        telegram_id=telegram_id,
        telegram_handle=telegram_handle,
    )
    db.add(user)
    await db.flush()
    await db.commit()
    return user, True


async def set_step(
    db: AsyncSession, user_id: uuid.UUID, step: OnboardingStep
) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.onboarding_step = int(step)
    await db.commit()


async def set_display_name(
    db: AsyncSession, user_id: uuid.UUID, name: str
) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.display_name = name
    await db.commit()


async def set_primary_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_code: str
) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.primary_goal = goal_code
    await db.commit()


async def mark_completed(db: AsyncSession, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.onboarding_step = int(OnboardingStep.COMPLETED)
    user.onboarding_completed_at = datetime.now(timezone.utc)
    await db.commit()


async def mark_skipped(db: AsyncSession, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    if not user:
        return
    user.onboarding_skipped = True
    await db.commit()


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
