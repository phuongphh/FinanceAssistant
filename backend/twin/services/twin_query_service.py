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
# When the actual net worth diverges from the projection's stored
# ``base_net_worth`` by more than this ratio, the cone no longer reflects
# the user's portfolio and we treat it as stale even if computed today.
# 10% is the smallest gap that visibly breaks the chart's anchor: any
# bigger and the "Hiện tại" dot drifts off the visible cone.
VALUE_STALENESS_THRESHOLD = Decimal("0.10")


@dataclass(frozen=True, slots=True)
class TwinSnapshot:
    latest_cone: list[dict[str, Any]] | None
    actual_nw: Decimal
    actual_breakdown: dict[str, Decimal]
    delta_vs_p50: Decimal | None
    cone_age_days: int | None
    is_stale: bool
    projection: TwinProjection | None = None
    is_value_stale: bool = False


async def get_twin_snapshot(db: AsyncSession, user_id: uuid.UUID) -> TwinSnapshot:
    """Return latest current-scenario cone and actual net-worth delta.

    This is intentionally read-only. It performs no writes and never flushes.
    """
    projection = await get_latest_projection(db, user_id, scenario=SCENARIO_CURRENT)
    actual_breakdown = await wealth_service.calculate_stored_current(db, user_id)
    actual = actual_breakdown.total
    by_type = getattr(actual_breakdown, "by_type", {})
    if projection is None:
        return TwinSnapshot(
            latest_cone=None,
            actual_nw=actual,
            actual_breakdown=by_type,
            delta_vs_p50=None,
            cone_age_days=None,
            is_stale=True,
            projection=None,
            is_value_stale=True,
        )

    now = datetime.now(timezone.utc)
    computed_at = projection.computed_at
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - computed_at).days)
    reference_p50 = _reference_p50(
        projection.cone_data, age_days, projection.horizon_years
    )
    base_net_worth = Decimal(str(getattr(projection, "base_net_worth", None) or 0))
    value_stale = _is_value_stale(actual, base_net_worth)
    return TwinSnapshot(
        latest_cone=projection.cone_data,
        actual_nw=actual,
        actual_breakdown=by_type,
        delta_vs_p50=None if reference_p50 is None else actual - reference_p50,
        cone_age_days=age_days,
        is_stale=age_days > STALE_AFTER_DAYS,
        projection=projection,
        is_value_stale=value_stale,
    )


def _is_value_stale(actual: Decimal, base_net_worth: Decimal) -> bool:
    """True when the cone's starting point no longer matches the wallet.

    Compares ``actual_nw`` to the projection's ``base_net_worth`` and flags
    the snapshot when they diverge by more than
    :data:`VALUE_STALENESS_THRESHOLD`. We anchor the ratio to the LARGER side
    so the check is symmetric: dropping from 2tr → 200tr and growing from
    200tr → 2tr both register as the same magnitude of staleness, instead
    of one direction looking like 90% and the other 900%.
    """
    actual_abs = abs(actual)
    base_abs = abs(base_net_worth)
    if actual_abs == 0 and base_abs == 0:
        return False
    denom = max(actual_abs, base_abs)
    if denom == 0:
        return False
    return abs(actual_abs - base_abs) / denom > VALUE_STALENESS_THRESHOLD


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
