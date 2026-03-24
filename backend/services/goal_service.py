import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.goal import Goal
from backend.models.user import User
from backend.schemas.goal import GoalCreate, GoalProgressUpdate, GoalUpdate


async def create_goal(
    db: AsyncSession, user_id: uuid.UUID, data: GoalCreate
) -> Goal:
    goal = Goal(
        user_id=user_id,
        goal_name=data.goal_name,
        target_amount=data.target_amount,
        current_amount=data.current_amount,
        deadline=data.deadline,
        priority=data.priority,
    )
    db.add(goal)
    await db.flush()
    await db.refresh(goal)
    return goal


async def get_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID
) -> Goal | None:
    stmt = select(Goal).where(
        Goal.id == goal_id,
        Goal.user_id == user_id,
        Goal.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_goals(
    db: AsyncSession, user_id: uuid.UUID, active_only: bool = True
) -> list[Goal]:
    stmt = select(Goal).where(
        Goal.user_id == user_id,
        Goal.deleted_at.is_(None),
    )
    if active_only:
        stmt = stmt.where(Goal.is_active.is_(True))
    stmt = stmt.order_by(Goal.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_goal(
    db: AsyncSession,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    data: GoalUpdate,
) -> Goal | None:
    goal = await get_goal(db, user_id, goal_id)
    if not goal:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    await db.flush()
    await db.refresh(goal)
    return goal


async def update_goal_progress(
    db: AsyncSession,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    data: GoalProgressUpdate,
) -> Goal | None:
    goal = await get_goal(db, user_id, goal_id)
    if not goal:
        return None
    goal.current_amount = data.current_amount
    await db.flush()
    await db.refresh(goal)
    return goal


async def delete_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID
) -> bool:
    goal = await get_goal(db, user_id, goal_id)
    if not goal:
        return False
    goal.deleted_at = datetime.utcnow()
    await db.flush()
    return True


async def set_monthly_income(
    db: AsyncSession, user_id: uuid.UUID, monthly_income: float
) -> User | None:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.monthly_income = monthly_income
    await db.flush()
    await db.refresh(user)
    return user
