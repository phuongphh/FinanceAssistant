"""Optimal trajectory simulation for Phase 4A.

MVP simplification: the optimal scenario assumes an immediate rebalance to the
wealth-level target allocation and a +10% monthly-savings habit improvement.
Tax, slippage, liquidity constraints, and transaction costs are intentionally
ignored for Phase 4A and must be disclosed in user-facing copy.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from numpy.typing import NDArray
import numpy as np

from backend.twin.allocation.target_allocation import get_target_allocation
from backend.twin.engine.monte_carlo import simulate_portfolio
from backend.wealth.ladder import WealthLevel


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
    """Simulate rebalanced target allocation with boosted savings.

    Args:
        user_portfolio: Current VND amounts by Twin asset class.
        wealth_level: One of the four VN wealth-level IDs/enums.
        horizon: Projection horizon in years.
        monthly_savings: Current monthly savings before boost.
        savings_boost: Multiplier, default 1.10 for +10% savings.
        paths: Number of Monte Carlo paths.
        seed: Optional deterministic seed.

    Returns:
        Same shape as ``simulate_portfolio``: ``(paths, horizon + 1)``.
    """
    if not user_portfolio:
        raise ValueError("user_portfolio must contain at least one asset class")
    total = sum(Decimal(str(value or 0)) for value in user_portfolio.values())
    if total <= 0:
        raise ValueError("user_portfolio total must be positive")

    target = get_target_allocation(wealth_level)
    rebalanced_amounts = {
        asset_class: (total * Decimal(str(weight))).quantize(Decimal("1"))
        for asset_class, weight in target.items()
        if weight > 0
    }
    boosted_savings = (
        Decimal(str(monthly_savings or 0)) * Decimal(str(savings_boost))
    ).quantize(Decimal("1"))
    return simulate_portfolio(
        rebalanced_amounts,
        boosted_savings,
        savings_split=target,
        horizon=horizon,
        paths=paths,
        seed=seed,
    )
