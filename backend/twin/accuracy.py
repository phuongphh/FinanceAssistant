"""Historical accuracy tracking for Financial Twin projections.

Before computing a fresh projection each week, the weekly updater calls
fill_previous_projection_accuracy() so the previous row captures what
actually happened.  This enables "prediction vs reality" reporting in
the morning briefing.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.twin_projection import TwinProjection
from backend.twin.services.twin_projection_service import SCENARIO_CURRENT
from backend.wealth.services import net_worth_calculator as wealth_service

logger = logging.getLogger(__name__)


async def fill_previous_projection_accuracy(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> bool:
    """Backfill actual_net_worth on the most recent projection that lacks it.

    Returns True if a row was updated, False if there was nothing to fill.
    Caller owns the transaction — this function only flushes.
    """
    stmt = (
        select(TwinProjection)
        .where(
            TwinProjection.user_id == user_id,
            TwinProjection.scenario == SCENARIO_CURRENT,
            TwinProjection.actual_net_worth.is_(None),
        )
        .order_by(TwinProjection.computed_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    projection = result.scalar_one_or_none()
    if projection is None:
        return False

    try:
        breakdown = await wealth_service.calculate_stored_current(db, user_id)
        actual = breakdown.total
    except Exception:
        logger.exception("accuracy: failed to fetch net worth for user=%s", user_id)
        return False

    projection.actual_net_worth = actual
    await db.flush()
    logger.info(
        "accuracy: filled projection=%s user=%s actual=%.2f",
        projection.id,
        user_id,
        actual,
    )
    return True


async def get_accuracy_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> AccuracySummary | None:
    """Return the most recent accuracy comparison for briefing display.

    Returns None when fewer than 2 projections exist or when no projection
    has actual_net_worth filled.
    """
    stmt = (
        select(TwinProjection)
        .where(
            TwinProjection.user_id == user_id,
            TwinProjection.scenario == SCENARIO_CURRENT,
        )
        .order_by(TwinProjection.computed_at.desc())
        .limit(10)
    )
    rows = list((await db.execute(stmt)).scalars().all())

    if len(rows) < 2:
        return None

    # Find the most recent projection that has actual_net_worth filled
    filled = next((r for r in rows if r.actual_net_worth is not None), None)
    if filled is None:
        return None

    predicted_p50 = _extract_p50_at_year_0(filled.cone_data)
    if predicted_p50 is None or predicted_p50 <= 0:
        return None

    actual = filled.actual_net_worth
    error_pct = (actual - predicted_p50) / predicted_p50 * Decimal("100")

    return AccuracySummary(
        predicted_p50=predicted_p50,
        actual=actual,
        error_pct=error_pct,
    )


class AccuracySummary:
    __slots__ = ("predicted_p50", "actual", "error_pct")

    def __init__(
        self,
        predicted_p50: Decimal,
        actual: Decimal,
        error_pct: Decimal,
    ) -> None:
        self.predicted_p50 = predicted_p50
        self.actual = actual
        self.error_pct = error_pct

    @property
    def tone(self) -> str:
        """Tone for the morning briefing message: reassure | celebrate | neutral."""
        if self.actual < self.predicted_p50 * Decimal("0.9"):
            return "reassure"
        if self.actual > self.predicted_p50 * Decimal("1.1"):
            return "celebrate"
        return "neutral"


def _extract_p50_at_year_0(cone_data: list[dict]) -> Decimal | None:
    """Return the P50 at year-0 (base year) from cone data."""
    if not cone_data:
        return None
    by_year = {int(point.get("year", -1)): point for point in cone_data}
    point = by_year.get(0) or cone_data[0]
    raw = point.get("p50")
    return Decimal(str(raw)) if raw is not None else None
