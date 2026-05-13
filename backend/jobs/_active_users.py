"""Shared helper: fetch users active within a recent window.

Every Phase 2 personality job (milestones, empathy, fun facts, seasonal
notifier, goal reminder) needs the same "users who've done *something*
in the last N days, are not deleted, have a telegram_id" query. Keeping
it in one place avoids five slightly-different definitions of "active".

Definition of active: at least one non-deleted expense created in the
window. Falling back to "ever" would send wake-up messages to users who
stopped using the bot — worse than silence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.user import User


async def get_active_users(
    db: AsyncSession,
    *,
    days: int,
    require_telegram_id: bool = True,
) -> list[User]:
    """Users with at least one non-deleted expense in the last ``days``.

    Filters to ``is_active=True`` and ``deleted_at IS NULL`` so soft-
    deleted accounts never get woken up. When ``require_telegram_id``
    is True (the default) users without a telegram_id are skipped since
    they can't receive messages anyway.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    active_ids_stmt = select(distinct(Expense.user_id)).where(
        Expense.created_at >= since,
        Expense.deleted_at.is_(None),
    )
    user_ids = [r[0] for r in (await db.execute(active_ids_stmt)).all()]
    if not user_ids:
        return []

    users_stmt = select(User).where(
        User.id.in_(user_ids),
        User.deleted_at.is_(None),
        User.is_active.is_(True),
    )
    if require_telegram_id:
        users_stmt = users_stmt.where(User.telegram_id.isnot(None))
    return list((await db.execute(users_stmt)).scalars())
