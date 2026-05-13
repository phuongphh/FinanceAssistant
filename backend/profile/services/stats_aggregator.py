from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, cast, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.feedback.models.feedback import Feedback
from backend.models.event import Event
from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.user import User
from backend.profile.services.wealth_level_mapper import WealthLevelMapper
from backend.wealth.models.asset import Asset
from backend.wealth.models.asset_snapshot import AssetSnapshot
from backend.wealth.services import net_worth_calculator


class ProfileStatsAggregator:
    """Compute fresh, auto-derived profile stats on demand."""

    def __init__(self, mapper: WealthLevelMapper | None = None) -> None:
        self.mapper = mapper or WealthLevelMapper()

    async def aggregate(self, db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
        user = await db.get(User, user_id)
        now = datetime.now(timezone.utc)
        account_age_days = self._account_age_days(user, now)
        net_worth = await net_worth_calculator.calculate(db, user_id)
        total = Decimal(net_worth.total or 0)

        month_start = date.today().replace(day=1)
        scalar_queries = [
            select(func.count(func.distinct(Asset.asset_type))).where(
                Asset.user_id == user_id,
                Asset.is_active.is_(True),
            ),
            select(func.count()).where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
            ),
            select(func.count()).where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= month_start,
            ),
            select(func.count()).where(
                Goal.user_id == user_id,
                Goal.deleted_at.is_(None),
                Goal.status == "active",
            ),
            select(func.count()).where(
                Goal.user_id == user_id,
                Goal.deleted_at.is_(None),
                Goal.status == "completed",
            ),
            select(func.count()).where(
                Event.user_id == user_id,
                Event.event_type == analytics.EventType.MORNING_BRIEFING_OPENED,
            ),
        ]
        (
            asset_types_count,
            transaction_count_total,
            transaction_count_this_month,
            goals_active,
            goals_completed,
            briefing_read_count,
        ) = [
            int((await db.execute(stmt)).scalar() or 0)
            for stmt in scalar_queries
        ]

        return {
            "account_age_days": account_age_days,
            "net_worth": total,
            "wealth_level": self.mapper.get_level(total),
            "wealth_progress": self.mapper.get_progress_to_next(total),
            "asset_types_count": min(asset_types_count, 6),
            "transaction_count_total": transaction_count_total,
            "transaction_count_this_month": transaction_count_this_month,
            "goals_active": goals_active,
            "goals_completed": goals_completed,
            "briefing_read_count": briefing_read_count,
            "current_streak": await self._compute_streak(db, user_id),
            "net_worth_change_pct": await self._net_worth_change_pct(
                db, user_id, total
            ),
        }

    def _account_age_days(self, user: User | None, now: datetime) -> int:
        if user is None or user.created_at is None:
            return 0
        created_at = user.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return max(0, (now - created_at).days)

    async def _compute_streak(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        activity_days = await self._activity_days(db, user_id)
        if not activity_days:
            return 1
        days = set(activity_days)
        today = date.today()
        current = today if today in days else max(days)
        streak = 0
        cursor = current
        while cursor in days:
            streak += 1
            cursor -= timedelta(days=1)
        return max(1, streak)

    async def _activity_days(self, db: AsyncSession, user_id: uuid.UUID) -> list[date]:
        expense_days = select(Expense.expense_date.label("activity_day")).where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
        )
        briefing_days = select(cast(Event.timestamp, Date).label("activity_day")).where(
            Event.user_id == user_id,
            Event.event_type == analytics.EventType.MORNING_BRIEFING_OPENED,
        )
        feedback_days = select(
            cast(Feedback.created_at, Date).label("activity_day")
        ).where(
            Feedback.user_id == user_id,
        )
        activity = union_all(
            expense_days, briefing_days, feedback_days
        ).subquery()
        stmt = select(func.distinct(activity.c.activity_day))
        result = await db.execute(stmt)
        return [d for d in result.scalars().all() if d is not None]

    async def _net_worth_change_pct(
        self, db: AsyncSession, user_id: uuid.UUID, current_net_worth: Decimal
    ) -> float | None:
        first_snapshot_date = (
            await db.execute(
                select(AssetSnapshot.snapshot_date)
                .where(AssetSnapshot.user_id == user_id)
                .order_by(AssetSnapshot.snapshot_date.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if first_snapshot_date is None:
            return None
        first = await net_worth_calculator.calculate_historical(
            db, user_id, first_snapshot_date
        )
        if first <= 0:
            return None
        return float((current_net_worth - first) / first * Decimal("100"))
