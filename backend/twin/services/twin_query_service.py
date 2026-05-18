"""Read-only Financial Twin query helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.twin_projection import TwinProjection
from backend.twin.services.twin_projection_service import SCENARIO_CURRENT
from backend.wealth.services import net_worth_calculator as wealth_service

STALE_AFTER_DAYS = 14


@dataclass(frozen=True, slots=True)
class TwinSnapshot:
    latest_cone: list[dict[str, Any]] | None
    actual_nw: Decimal
    actual_breakdown: dict[str, Decimal]
    delta_vs_p50: Decimal | None
    cone_age_days: int | None
    is_stale: bool
    projection: TwinProjection | None = None


async def get_twin_snapshot(db: AsyncSession, user_id: uuid.UUID) -> TwinSnapshot:
    """Return latest current-scenario cone and actual net-worth delta.

    This is intentionally read-only. It performs no writes and never flushes.
    """
    projection = await get_latest_projection(db, user_id, scenario=SCENARIO_CURRENT)
    actual_breakdown = await wealth_service.calculate_stored_current(db, user_id)
    actual = actual_breakdown.total
    if projection is None:
        return TwinSnapshot(
            latest_cone=None,
            actual_nw=actual,
            actual_breakdown=actual_breakdown.by_type,
            delta_vs_p50=None,
            cone_age_days=None,
            is_stale=True,
            projection=None,
        )

    now = datetime.now(timezone.utc)
    computed_at = projection.computed_at
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - computed_at).days)
    reference_p50 = _reference_p50(
        projection.cone_data, age_days, projection.horizon_years
    )
    return TwinSnapshot(
        latest_cone=projection.cone_data,
        actual_nw=actual,
        actual_breakdown=actual_breakdown.by_type,
        delta_vs_p50=None if reference_p50 is None else actual - reference_p50,
        cone_age_days=age_days,
        is_stale=age_days > STALE_AFTER_DAYS,
        projection=projection,
    )


async def get_latest_projection(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    scenario: str | None = None,
) -> TwinProjection | None:
    stmt = select(TwinProjection).where(TwinProjection.user_id == user_id)
    if scenario is not None:
        stmt = stmt.where(TwinProjection.scenario == scenario)
    stmt = stmt.order_by(TwinProjection.computed_at.desc()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


def _reference_p50(
    cone_data: list[dict[str, Any]], age_days: int, horizon_years: int
) -> Decimal | None:
    if not cone_data:
        return None
    year_index = min(horizon_years, age_days // 365)
    by_year = {int(point.get("year", -1)): point for point in cone_data}
    point = by_year.get(year_index) or cone_data[0]
    raw = point.get("p50")
    return Decimal(str(raw)) if raw is not None else None
