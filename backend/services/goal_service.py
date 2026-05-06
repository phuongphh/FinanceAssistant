"""Goal CRUD — Phase 3.8 Epic 5 rewrite.

Phase 3A had a stub; Epic 5 promotes goals to first-class with
template linkage, status enum, projection cache, and proper
ownership-checked CRUD. The wizard handler
(``backend.bot.handlers.goal_entry``) and the agent tool
(``backend.agent.tools.get_goals``) both go through this service.

Layer contract: service flushes only — caller commits.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.goal import Goal
from backend.models.user import User
from backend.schemas.goal import (
    GoalCreate,
    GoalProgressUpdate,
    GoalUpdate,
)


# ---------------------------------------------------------------------
# Mutation API
# ---------------------------------------------------------------------


async def create_goal(
    db: AsyncSession, user_id: uuid.UUID, data: GoalCreate
) -> Goal:
    """Create a goal. ``status`` defaults to 'active'; the wizard
    flips this to 'completed' if ``current_amount >= target_amount``
    at create time (rare but possible — user adds an already-met
    'quỹ khẩn cấp')."""
    initial_status = "active"
    if (
        data.current_amount is not None
        and data.target_amount > 0
        and data.current_amount >= data.target_amount
    ):
        initial_status = "completed"

    goal = Goal(
        user_id=user_id,
        name=data.name,
        template_id=data.template_id,
        icon=data.icon,
        target_amount=Decimal(data.target_amount),
        current_amount=Decimal(data.current_amount or 0),
        target_date=data.target_date,
        priority=data.priority or 5,
        status=initial_status,
        completed_at=datetime.utcnow() if initial_status == "completed" else None,
    )
    db.add(goal)
    await db.flush()
    return goal


async def get_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID
) -> Goal | None:
    """Ownership-checked single fetch. Returns None when not found
    or owned by another user (deliberately doesn't distinguish so
    we don't leak other users' goal ids)."""
    stmt = select(Goal).where(
        Goal.id == goal_id,
        Goal.user_id == user_id,
        Goal.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_goals(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    active_only: bool = True,
) -> list[Goal]:
    """List the user's goals.

    ``active_only=True`` (default) means status='active'. Set False
    to include completed / paused / abandoned goals (used by the
    "Lịch sử mục tiêu" view + agent tool when explicitly asked
    'mục tiêu đã đạt được')."""
    stmt = select(Goal).where(
        Goal.user_id == user_id,
        Goal.deleted_at.is_(None),
    )
    if active_only:
        stmt = stmt.where(Goal.status == "active")
    # Priority asc (1=highest), then by creation date desc — newest
    # within a priority band shows first.
    stmt = stmt.order_by(Goal.priority.asc(), Goal.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def update_goal(
    db: AsyncSession,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    data: GoalUpdate,
) -> Goal | None:
    """Apply a partial update. Returns None when the goal isn't
    owned by the user — caller maps to 404."""
    goal = await get_goal(db, user_id, goal_id)
    if not goal:
        return None
    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(goal, field, value)
    # If status moved to 'completed' for the first time, stamp
    # completed_at so the celebration logic (Phase 4) fires once.
    if (
        payload.get("status") == "completed"
        and goal.completed_at is None
    ):
        goal.completed_at = datetime.utcnow()
    await db.flush()
    return goal


async def update_goal_progress(
    db: AsyncSession,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    data: GoalProgressUpdate,
) -> Goal | None:
    """Update ``current_amount`` only — the most common edit. Auto-
    flips ``status='completed'`` (and stamps ``completed_at``) when
    the new amount hits the target. We DON'T un-complete on
    decrement (user typo'd) — keep that flow explicit via
    ``update_goal``."""
    goal = await get_goal(db, user_id, goal_id)
    if not goal:
        return None
    goal.current_amount = Decimal(data.current_amount)
    if (
        Decimal(goal.target_amount or 0) > 0
        and goal.current_amount >= Decimal(goal.target_amount)
        and goal.status != "completed"
    ):
        goal.status = "completed"
        goal.completed_at = datetime.utcnow()
    goal.updated_at = datetime.utcnow()
    await db.flush()
    return goal


async def delete_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID
) -> bool:
    """Soft delete via ``deleted_at`` timestamp. Returns False when
    the goal isn't owned. Distinct from setting ``status='abandoned'``
    — abandon = "I gave up but want to remember"; delete = "this
    was a mistake, hide it"."""
    goal = await get_goal(db, user_id, goal_id)
    if not goal:
        return False
    goal.deleted_at = datetime.utcnow()
    await db.flush()
    return True


async def set_monthly_income(
    db: AsyncSession, user_id: uuid.UUID, monthly_income: float
) -> User | None:
    """Legacy ``users.monthly_income`` setter — predates the
    IncomeStream wizard. Kept for the REST router until it's
    deprecated in Phase 1."""
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        return None
    user.monthly_income = monthly_income
    await db.flush()
    return user
