"""Financial Twin projection orchestration and persistence.

Layer contract: this service may ``flush`` to surface generated IDs, but it
never commits. Routers, schedulers, and background workers own transaction
boundaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.twin_projection import TwinProjection
from backend.services import cashflow_service
from backend.twin.engine import ENGINE_VERSION
from backend.twin.engine.cone_aggregator import ConePoint, aggregate_cone
from backend.twin.engine.monte_carlo import simulate_portfolio
from backend.wealth.services import asset_service
from backend.wealth.services import net_worth_calculator as wealth_service

DEFAULT_ENGINE_VERSION = ENGINE_VERSION
DEFAULT_SIM_PATHS = 1000
DEFAULT_HORIZON_YEARS = 10
SCENARIO_CURRENT = "current"
SCENARIO_OPTIMAL = "optimal"
Scenario = Literal["current", "optimal", "both"]

_ASSET_TYPE_TO_TWIN_CLASS = {
    "cash": "cash_savings",
    "crypto": "crypto",
    "gold": "gold",
    "real_estate": "real_estate_vn",
    "stock": "stocks_vn",
    "other": "cash_savings",
}


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    base_net_worth: Decimal
    monthly_savings: Decimal
    allocation_amounts: dict[str, Decimal]
    allocation_weights: dict[str, Decimal]


def engine_version_for_projection() -> str:
    """Return the engine version to stamp on ``twin_projections`` rows."""
    return DEFAULT_ENGINE_VERSION


async def compute_and_store(
    db: AsyncSession,
    user_id: uuid.UUID,
    scenario: Scenario = "both",
    *,
    horizon: int = DEFAULT_HORIZON_YEARS,
    paths: int = DEFAULT_SIM_PATHS,
    seed: int | None = None,
) -> list[TwinProjection]:
    """Compute current/optimal cones and add projection rows to the session.

    ``scenario="both"`` is the Phase 4A default so current and optimal share
    one portfolio/cashflow read. Passing a single scenario is kept for tests and
    future admin tooling. Caller must commit or roll back.
    """
    if scenario not in {SCENARIO_CURRENT, SCENARIO_OPTIMAL, "both"}:
        raise ValueError(f"Unsupported Twin scenario: {scenario}")
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if paths <= 0:
        raise ValueError("paths must be positive")

    snapshot = await load_portfolio_snapshot(db, user_id)
    if snapshot.base_net_worth <= 0:
        raise ValueError("Twin projection requires at least one active asset")

    scenarios = (
        [SCENARIO_CURRENT, SCENARIO_OPTIMAL] if scenario == "both" else [scenario]
    )
    projections: list[TwinProjection] = []
    for index, scenario_name in enumerate(scenarios):
        monthly_savings, savings_split = _scenario_inputs(snapshot, scenario_name)
        sim = simulate_portfolio(
            snapshot.allocation_amounts,
            monthly_savings,
            savings_split=savings_split,
            horizon=horizon,
            paths=paths,
            seed=None if seed is None else seed + index,
        )
        cone = aggregate_cone(sim)
        projection = TwinProjection(
            user_id=user_id,
            horizon_years=horizon,
            scenario=scenario_name,
            base_net_worth=snapshot.base_net_worth,
            monthly_savings=monthly_savings,
            allocation_snapshot=_decimal_mapping_to_json(snapshot.allocation_weights),
            cone_data=_cone_to_json(cone),
            sim_paths=paths,
            seed=None if seed is None else seed + index,
            engine_version=engine_version_for_projection(),
        )
        db.add(projection)
        projections.append(projection)

    await db.flush()
    return projections


async def load_portfolio_snapshot(
    db: AsyncSession, user_id: uuid.UUID
) -> PortfolioSnapshot:
    """Load current assets through wealth services and normalize for the engine."""
    net_worth = await wealth_service.calculate_stored_current(db, user_id)
    monthly_savings = await cashflow_service.last_3_month_avg_savings(db, user_id)
    assets = await asset_service.get_user_assets(db, user_id)

    allocation_amounts: dict[str, Decimal] = {}
    for asset in assets:
        twin_class = _map_asset_to_twin_class(asset.asset_type, asset.subtype)
        allocation_amounts[twin_class] = allocation_amounts.get(
            twin_class, Decimal(0)
        ) + Decimal(asset.current_value or 0)

    total = net_worth.total
    allocation_weights = (
        {
            asset_class: (amount / total).quantize(Decimal("0.0001"))
            for asset_class, amount in allocation_amounts.items()
        }
        if total > 0
        else {}
    )
    return PortfolioSnapshot(
        base_net_worth=total,
        monthly_savings=monthly_savings,
        allocation_amounts=allocation_amounts,
        allocation_weights=allocation_weights,
    )


def _map_asset_to_twin_class(asset_type: str, subtype: str | None) -> str:
    if asset_type == "stock" and subtype == "foreign_stock":
        return "stocks_global"
    return _ASSET_TYPE_TO_TWIN_CLASS.get(asset_type, "cash_savings")


def _scenario_inputs(
    snapshot: PortfolioSnapshot,
    scenario: str,
) -> tuple[Decimal, Mapping[str, Decimal] | None]:
    if scenario == SCENARIO_CURRENT:
        return snapshot.monthly_savings, snapshot.allocation_weights or None
    if scenario == SCENARIO_OPTIMAL:
        # Conservative Phase 4A placeholder until Epic 5 introduces target allocation:
        # keep the same allocation but model a +10% savings habit improvement.
        return (snapshot.monthly_savings * Decimal("1.10")).quantize(
            Decimal("1")
        ), snapshot.allocation_weights or None
    raise ValueError(f"Unsupported Twin scenario: {scenario}")


def _cone_to_json(cone: list[ConePoint]) -> list[dict[str, int | str]]:
    return [
        {
            "year": point.year,
            "p10": str(point.p10),
            "p50": str(point.p50),
            "p90": str(point.p90),
        }
        for point in cone
    ]


def _decimal_mapping_to_json(values: Mapping[str, Decimal]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}
