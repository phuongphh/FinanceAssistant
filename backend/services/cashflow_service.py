"""Cashflow read helpers shared by projections and UI surfaces."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services import goal_projection


async def last_3_month_avg_savings(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    today: date | None = None,
) -> Decimal:
    """Return historical 3-month average savings (income minus expenses).

    This wraps the existing goal-projection calculation so Phase 4A Twin reads
    cashflow through a named cashflow service without duplicating SQL.
    """
    return await goal_projection.get_avg_monthly_savings(db, user_id, today=today)
