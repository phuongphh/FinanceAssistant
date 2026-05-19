"""Optimal trajectory simulation for Phase 4A.

The optimal scenario combines two levers — a rebalance toward the wealth-tier
target allocation and a +10% monthly-savings habit improvement. A
*Pareto-aware* guard guarantees the optimal scenario never strictly dominates
itself out of the user's favor: for portfolios whose current expected return
already exceeds the rule-of-thumb target (typically aggressive crypto- or
real-estate-heavy allocations), we keep the user's current weights and apply
only the savings nudge. Otherwise the comparison would label a *risk
reduction* as "Tối ưu" while showing strictly lower P50/P90 — a UX bug.

Tax, slippage, liquidity constraints, and transaction costs are intentionally
ignored for Phase 4A and must be disclosed in user-facing copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Mapping

from numpy.typing import NDArray
import numpy as np

from backend.twin.allocation.target_allocation import get_target_allocation
from backend.twin.engine.distributions import get_distribution
from backend.twin.engine.monte_carlo import simulate_portfolio
from backend.wealth.ladder import WealthLevel


OptimalStrategy = Literal["rebalance_to_target", "savings_only"]


@dataclass(frozen=True, slots=True)
class OptimalPlan:
    """Resolved optimal allocation + which strategy produced it.

    ``allocation_weights`` sum to ~1.0 and are used as both the rebalanced
    portfolio and the ``savings_split`` for new contributions.
    """

    strategy: OptimalStrategy
    allocation_weights: dict[str, float]
    expected_return_current: float
    expected_return_chosen: float
    expected_return_target: float


def resolve_optimal_plan(
    user_portfolio: Mapping[str, Decimal | int | float],
    wealth_level: WealthLevel | str,
) -> OptimalPlan:
    """Pick the optimal allocation for a user given their current weights.

    Returns the user's *current* weights when the wealth-tier target would
    reduce expected portfolio return — the savings boost still differentiates
    the scenario from "Hiện tại" without misleading the user with strictly
    worse P50/P90 numbers.
    """
    if not user_portfolio:
        raise ValueError("user_portfolio must contain at least one asset class")
    total = sum(Decimal(str(value or 0)) for value in user_portfolio.values())
    if total <= 0:
        raise ValueError("user_portfolio total must be positive")

    current_weights = {
        asset_class: float(Decimal(str(value or 0)) / total)
        for asset_class, value in user_portfolio.items()
        if Decimal(str(value or 0)) > 0
    }
    target_weights = {
        asset_class: float(weight)
        for asset_class, weight in get_target_allocation(wealth_level).items()
        if weight > 0
    }

    mu_current = _expected_portfolio_return(current_weights)
    mu_target = _expected_portfolio_return(target_weights)

    if mu_target >= mu_current:
        return OptimalPlan(
            strategy="rebalance_to_target",
            allocation_weights=target_weights,
            expected_return_current=mu_current,
            expected_return_chosen=mu_target,
            expected_return_target=mu_target,
        )
    return OptimalPlan(
        strategy="savings_only",
        allocation_weights=current_weights,
        expected_return_current=mu_current,
        expected_return_chosen=mu_current,
        expected_return_target=mu_target,
    )


def simulate_optimal(
    user_portfolio: Mapping[str, Decimal | int | float],
    wealth_level: WealthLevel | str,
    horizon: int,
    *,
    monthly_savings: Decimal | int | float = Decimal("0"),
    savings_boost: Decimal | int | float = Decimal("1.10"),
    paths: int = 1000,
    seed: int | None = None,
) -> NDArray[np.float64]:
    """Simulate the Pareto-aware optimal trajectory with boosted savings.

    Args:
        user_portfolio: Current VND amounts by Twin asset class.
        wealth_level: One of the VN wealth-level IDs/enums.
        horizon: Projection horizon in years.
        monthly_savings: Current monthly savings before boost.
        savings_boost: Multiplier, default 1.10 for +10% savings.
        paths: Number of Monte Carlo paths.
        seed: Optional deterministic seed.

    Returns:
        Same shape as ``simulate_portfolio``: ``(paths, horizon + 1)``.
    """
    plan = resolve_optimal_plan(user_portfolio, wealth_level)
    total = sum(Decimal(str(value or 0)) for value in user_portfolio.values())
    chosen_amounts = {
        asset_class: (total * Decimal(str(weight))).quantize(Decimal("1"))
        for asset_class, weight in plan.allocation_weights.items()
    }
    boosted_savings = (
        Decimal(str(monthly_savings or 0)) * Decimal(str(savings_boost))
    ).quantize(Decimal("1"))
    return simulate_portfolio(
        chosen_amounts,
        boosted_savings,
        savings_split=plan.allocation_weights,
        horizon=horizon,
        paths=paths,
        seed=seed,
    )


def _expected_portfolio_return(weights: Mapping[str, float]) -> float:
    """Sum weight * μ across the configured Twin distributions."""
    total = 0.0
    for asset_class, weight in weights.items():
        if weight <= 0:
            continue
        try:
            dist = get_distribution(asset_class)
        except ValueError:
            # Unknown asset (e.g. legacy data) — treat as zero return, no panic.
            continue
        total += float(weight) * float(dist.mu)
    return total
