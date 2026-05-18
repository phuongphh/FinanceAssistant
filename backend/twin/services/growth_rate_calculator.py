"""Fast present-anchor calculations for Phase 4.3 Twin comprehension."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.services import net_worth_calculator

MIN_GROWTH_DAYS = 30
ROLLING_DAYS = 90
WEEK_DAYS = 7
SMALL_DELTA_THRESHOLD_VND = Decimal("100000")
LARGE_VOLATILITY_RATIO = Decimal("0.30")


@dataclass(frozen=True, slots=True)
class GrowthRateSnapshot:
    current_net_worth: Decimal
    weekly_delta: Decimal | None
    monthly_growth_rate: Decimal | None
    days_observed: int
    has_enough_data: bool
    volatility_review_required: bool = False


async def calculate_growth_snapshot(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    current_net_worth: Decimal | None = None,
    today: date | None = None,
) -> GrowthRateSnapshot:
    """Return weekly delta and 90-day monthly growth without live repricing.

    Uses indexed ``asset_snapshots(user_id, snapshot_date)`` historical reads.
    The GET path remains light: no Monte Carlo recompute and no external APIs.
    """
    today = today or date.today()
    current = Decimal(current_net_worth or 0)
    if current_net_worth is None:
        current = (
            await net_worth_calculator.calculate_stored_current(db, user_id)
        ).total

    days_observed = await _days_observed(db, user_id, today=today)
    weekly_previous = await net_worth_calculator.calculate_historical(
        db, user_id, today - timedelta(days=WEEK_DAYS)
    )
    weekly_delta = (
        current - weekly_previous if weekly_previous != 0 or current != 0 else None
    )

    has_enough = days_observed >= MIN_GROWTH_DAYS
    monthly_rate: Decimal | None = None
    if has_enough:
        start_days = min(ROLLING_DAYS, days_observed)
        baseline = await net_worth_calculator.calculate_historical(
            db, user_id, today - timedelta(days=start_days)
        )
        monthly_rate = ((current - baseline) / Decimal(start_days)) * Decimal(30)
        monthly_rate = monthly_rate.quantize(Decimal("1"))

    volatility = False
    yesterday = await net_worth_calculator.calculate_historical(
        db, user_id, today - timedelta(days=1)
    )
    if yesterday > 0:
        volatility = abs(current - yesterday) / yesterday > LARGE_VOLATILITY_RATIO

    return GrowthRateSnapshot(
        current_net_worth=current,
        weekly_delta=weekly_delta,
        monthly_growth_rate=monthly_rate,
        days_observed=days_observed,
        has_enough_data=has_enough,
        volatility_review_required=volatility,
    )


async def _days_observed(db: AsyncSession, user_id: uuid.UUID, *, today: date) -> int:
    stmt = text("""
        SELECT MIN(snapshot_date) AS first_date
        FROM asset_snapshots
        WHERE user_id = :user_id
          AND snapshot_date <= :today
        """).bindparams(bindparam("user_id"), bindparam("today"))
    result = await db.execute(stmt, {"user_id": user_id, "today": today})
    first_date = result.scalar()
    if first_date is None:
        return 0
    return max(0, (today - first_date).days)


def is_small_delta(delta: Decimal | None) -> bool:
    return delta is None or abs(Decimal(delta)) < SMALL_DELTA_THRESHOLD_VND
