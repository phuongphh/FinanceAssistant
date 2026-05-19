"""Pareto-aware optimal trajectory guarantees.

Regression coverage for the screenshot bug where an aggressive crypto- and
real-estate-heavy portfolio rendered the "Tối ưu" scenario with strictly
lower P50/P90 than "Hiện tại". The engine now keeps the user's allocation
whenever rebalancing toward the wealth-tier target would *reduce* expected
return — the +10% savings boost still differentiates the two scenarios.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.twin.engine.cone_aggregator import aggregate_cone
from backend.twin.engine.monte_carlo import simulate_portfolio
from backend.twin.engine.optimal_trajectory import (
    resolve_optimal_plan,
    simulate_optimal,
)
from backend.twin.services import twin_api_service
from backend.wealth.ladder import WealthLevel


def _weights(amounts):
    total = sum(Decimal(str(v)) for v in amounts.values())
    return {a: float(Decimal(str(v)) / total) for a, v in amounts.items()}


def test_resolve_plan_picks_savings_only_when_current_outperforms_target():
    """Aggressive crypto+RE portfolio whose μ exceeds the HNW target's μ."""
    base = Decimal("15_000_000_000")
    portfolio = {
        "real_estate_vn": base * Decimal("0.609"),
        "crypto": base * Decimal("0.204"),
        "stocks_vn": base * Decimal("0.184"),
        "cash_savings": base * Decimal("0.003"),
    }

    plan = resolve_optimal_plan(portfolio, WealthLevel.HIGH_NET_WORTH)

    assert plan.strategy == "savings_only"
    assert plan.expected_return_current > plan.expected_return_target
    assert plan.allocation_weights["crypto"] == pytest.approx(0.204, rel=1e-3)
    assert plan.allocation_weights["real_estate_vn"] == pytest.approx(0.609, rel=1e-3)


def test_resolve_plan_picks_rebalance_when_target_improves_expected_return():
    """Moderate stocks/gold/cash portfolio whose μ is below the mass-affluent target."""
    portfolio = {
        "stocks_vn": Decimal("300_000_000"),
        "gold": Decimal("100_000_000"),
        "cash_savings": Decimal("100_000_000"),
    }

    plan = resolve_optimal_plan(portfolio, WealthLevel.MASS_AFFLUENT)

    assert plan.strategy == "rebalance_to_target"
    assert plan.expected_return_chosen >= plan.expected_return_current


def test_optimal_pareto_dominates_current_for_aggressive_portfolio():
    """Regression: optimal P10/P50/P90 must never be strictly lower than current."""
    base = Decimal("15_000_000_000")
    portfolio = {
        "real_estate_vn": base * Decimal("0.609"),
        "crypto": base * Decimal("0.204"),
        "stocks_vn": base * Decimal("0.184"),
        "cash_savings": base * Decimal("0.003"),
    }
    monthly = Decimal("100_000_000")
    horizon, paths, seed = 10, 1_000, 42

    current_sim = simulate_portfolio(
        portfolio,
        monthly,
        savings_split=_weights(portfolio),
        horizon=horizon,
        paths=paths,
        seed=seed,
    )
    optimal_sim = simulate_optimal(
        portfolio,
        WealthLevel.HIGH_NET_WORTH,
        horizon,
        monthly_savings=monthly,
        paths=paths,
        seed=seed,
    )

    cur = aggregate_cone(current_sim)[-1]
    opt = aggregate_cone(optimal_sim)[-1]

    # Same seed + same allocation (savings_only) → identical random shocks,
    # only the savings stream differs. Every percentile must move up.
    assert opt.p10 >= cur.p10
    assert opt.p50 >= cur.p50
    assert opt.p90 >= cur.p90
    # And actually strictly above on the median, by at least the boosted savings.
    assert opt.p50 > cur.p50


def test_derive_optimal_strategy_detects_savings_only_vs_rebalance():
    current = SimpleNamespace(
        allocation_snapshot={
            "real_estate_vn": "0.609",
            "crypto": "0.204",
            "stocks_vn": "0.184",
            "cash_savings": "0.003",
        }
    )
    # Same weights → engine kept the user's allocation.
    optimal_same = SimpleNamespace(
        allocation_snapshot=dict(current.allocation_snapshot)
    )
    assert (
        twin_api_service._derive_optimal_strategy(current, optimal_same)
        == "savings_only"
    )

    # Different weights → engine rebalanced to the wealth-tier target.
    optimal_rebalance = SimpleNamespace(
        allocation_snapshot={
            "stocks_vn": "0.35",
            "stocks_global": "0.15",
            "crypto": "0.05",
            "gold": "0.15",
            "cash_savings": "0.15",
            "real_estate_vn": "0.15",
        }
    )
    assert (
        twin_api_service._derive_optimal_strategy(current, optimal_rebalance)
        == "rebalance_to_target"
    )

    assert twin_api_service._derive_optimal_strategy(None, optimal_same) is None
    assert twin_api_service._derive_optimal_strategy(current, None) is None


def test_strategy_copy_returns_distinct_tooltip_per_strategy():
    rebalance = twin_api_service._strategy_copy("rebalance_to_target")
    savings_only = twin_api_service._strategy_copy("savings_only")
    default = twin_api_service._strategy_copy(None)

    assert rebalance["tooltip"]
    assert savings_only["tooltip"]
    assert rebalance["tooltip"] != savings_only["tooltip"]
    # Unknown strategy must fall back to the rebalance tooltip rather than empty.
    assert default["tooltip"] == rebalance["tooltip"]
    # Savings-only CTA copy clearly states no rebalance is suggested.
    assert "giữ nguyên" in savings_only["cta_savings"].lower()


def test_optimal_still_boosts_returns_for_conservative_portfolio():
    """When the target genuinely outperforms the user, rebalance + boost wins."""
    portfolio = {
        "cash_savings": Decimal("400_000_000"),
        "gold": Decimal("100_000_000"),
    }
    monthly = Decimal("10_000_000")
    horizon, paths, seed = 10, 1_000, 42

    current_sim = simulate_portfolio(
        portfolio,
        monthly,
        savings_split=_weights(portfolio),
        horizon=horizon,
        paths=paths,
        seed=seed,
    )
    optimal_sim = simulate_optimal(
        portfolio,
        WealthLevel.MASS_AFFLUENT,
        horizon,
        monthly_savings=monthly,
        paths=paths,
        seed=seed,
    )

    assert optimal_sim[:, -1].mean() > current_sim[:, -1].mean()
