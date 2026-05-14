from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User

STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"


async def is_user_allowed(db: AsyncSession, user_id) -> bool:
    """Return False when an admin manually suspended the user."""
    status = await db.scalar(select(User.manual_status).where(User.id == user_id))
    return status != STATUS_SUSPENDED
