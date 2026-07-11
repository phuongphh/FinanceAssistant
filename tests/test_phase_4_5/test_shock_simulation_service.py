"""Phase 4.5 / E1 / Issue #1.1 — shock_simulation_service.

Covers the pure core: severity bucketing is deterministic, ``simulate_shock``
runs the real Monte Carlo engine paired (shocked = baseline minus a one-time
outflow) so deltas are non-positive, an over-net-worth shock floors at zero
rather than crashing, and empty/zero portfolios + non-positive shocks raise.

We run with a low ``paths`` + fixed ``seed`` so the sim is fast and reproducible.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services.decision.shock_simulation_service import (
    ShockSeverity,
    classify_severity,
    simulate_shock,
)
from backend.twin.services.twin_projection_service import PortfolioSnapshot


def _snapshot(net_worth: Decimal = Decimal(1_000_000_000)) -> PortfolioSnapshot:
    amounts = {
        "cash_savings": net_worth * Decimal("0.3"),
        "stocks_vn": net_worth * Decimal("0.4"),
        "gold": net_worth * Decimal("0.3"),
    }
    total = sum(amounts.values(), Decimal(0))
    weights = {k: (v / total) for k, v in amounts.items()}
    return PortfolioSnapshot(
        base_net_worth=net_worth,
        monthly_savings=Decimal(5_000_000),
        allocation_amounts=amounts,
        allocation_weights=weights,
    )


# --------------------------------------------------------------------------
# classify_severity
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ratio,expected",
    [
        (Decimal("0.05"), ShockSeverity.LIGHT),
        (Decimal("0.14"), ShockSeverity.LIGHT),
        (Decimal("0.15"), ShockSeverity.MODERATE),  # boundary is exclusive below
        (Decimal("0.30"), ShockSeverity.MODERATE),
        (Decimal("0.50"), ShockSeverity.HEAVY),
        (Decimal("0.60"), ShockSeverity.SEVERE),
        (Decimal("0.90"), ShockSeverity.SEVERE),
    ],
)
def test_classify_severity_buckets(ratio, expected):
    net = Decimal(1_000_000_000)
    assert classify_severity(net * ratio, net) == expected


def test_classify_severity_zero_net_worth_is_severe():
    assert classify_severity(Decimal(1), Decimal(0)) == ShockSeverity.SEVERE


# --------------------------------------------------------------------------
# simulate_shock
# --------------------------------------------------------------------------


def test_simulate_shock_delta_is_non_positive():
    snap = _snapshot()
    result = simulate_shock(snap, Decimal(200_000_000), horizon=5, paths=200, seed=42)
    # A withdrawal can only lower or hold the trajectory.
    assert result.delta_p10 <= 0
    assert result.delta_p50 <= 0
    assert result.delta_p90 <= 0
    assert result.shock_amount == Decimal(200_000_000)
    assert result.base_net_worth == snap.base_net_worth
    assert result.severity == ShockSeverity.MODERATE


def test_simulate_shock_is_deterministic_with_seed():
    snap = _snapshot()
    a = simulate_shock(snap, Decimal(150_000_000), horizon=5, paths=200, seed=7)
    b = simulate_shock(snap, Decimal(150_000_000), horizon=5, paths=200, seed=7)
    assert a.shocked_final.p50 == b.shocked_final.p50
    assert a.delta_p50 == b.delta_p50


def test_simulate_shock_over_net_worth_floors_at_zero():
    snap = _snapshot(Decimal(100_000_000))
    # Shock bigger than net worth — floors at zero rather than going negative.
    result = simulate_shock(snap, Decimal(500_000_000), horizon=3, paths=200, seed=1)
    assert result.shocked_final.p10 >= 0
    assert result.severity == ShockSeverity.SEVERE
    assert result.impact_ratio == Decimal(5)


def test_simulate_shock_rejects_non_positive_shock():
    snap = _snapshot()
    with pytest.raises(ValueError):
        simulate_shock(snap, Decimal(0))
    with pytest.raises(ValueError):
        simulate_shock(snap, Decimal(-1))


def test_simulate_shock_rejects_empty_portfolio():
    empty = PortfolioSnapshot(
        base_net_worth=Decimal(0),
        monthly_savings=Decimal(0),
        allocation_amounts={},
        allocation_weights={},
    )
    with pytest.raises(ValueError):
        simulate_shock(empty, Decimal(100_000_000))
