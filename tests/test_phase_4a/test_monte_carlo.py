import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from backend.twin.engine import ENGINE_VERSION
from backend.twin.engine.cone_aggregator import aggregate_cone
from backend.twin.engine.distributions import ASSET_CLASSES, get_distribution
from backend.twin.engine.monte_carlo import simulate_portfolio, simulate_single_asset
from backend.twin.services.twin_projection_service import engine_version_for_projection


def test_all_asset_distributions_are_positive():
    for asset_class in ASSET_CLASSES:
        dist = get_distribution(asset_class)
        assert dist.mu != 0
        assert dist.sigma > 0
        assert dist.source_note


def test_single_asset_is_deterministic_and_finite():
    dist = get_distribution("stocks_vn")
    first = simulate_single_asset(Decimal("100000000"), Decimal("0"), dist, 10, seed=42)
    second = simulate_single_asset(Decimal("100000000"), Decimal("0"), dist, 10, seed=42)

    assert first.shape == (1000, 11)
    np.testing.assert_array_equal(first, second)
    assert np.isfinite(first).all()


def test_single_asset_p50_sanity_for_stocks_vn():
    initial = Decimal("100000000")
    dist = get_distribution("stocks_vn")
    result = simulate_single_asset(initial, Decimal("0"), dist, 10, paths=10000, seed=7)
    p50_year_10 = np.percentile(result[:, 10], 50)
    expected = float(initial) * (1.11 ** 10)

    assert p50_year_10 == pytest.approx(expected, rel=0.10)


def test_portfolio_requires_weight_allocation_sum_and_runs_fast_enough():
    allocation = {
        "stocks_vn": Decimal("0.50"),
        "gold": Decimal("0.20"),
        "cash_savings": Decimal("0.20"),
        "crypto": Decimal("0.10"),
    }
    assert sum(allocation.values()) == pytest.approx(Decimal("1.0"), abs=Decimal("0.001"))

    result = simulate_portfolio(
        allocation,
        Decimal("15000000"),
        savings_split=allocation,
        horizon=10,
        base_net_worth=Decimal("500000000"),
        seed=42,
    )

    assert result.shape == (1000, 11)
    assert np.isfinite(result).all()


def test_cone_aggregator_year_zero_and_monotonic():
    result = simulate_portfolio(
        {"stocks_vn": Decimal("300000000"), "gold": Decimal("100000000")},
        Decimal("10000000"),
        savings_split={"stocks_vn": Decimal("0.75"), "gold": Decimal("0.25")},
        horizon=10,
        seed=42,
    )
    cone = aggregate_cone(result)

    assert cone[0].year == 0
    assert cone[0].p10 == cone[0].p50 == cone[0].p90 == Decimal("4.0000E+8")
    for point in cone:
        assert point.p10 <= point.p50 <= point.p90
        assert point.p10 % Decimal("1000") == 0


def test_mass_affluent_seed_42_golden_cone():
    result = simulate_portfolio(
        {
            "stocks_vn": Decimal("300000000"),
            "gold": Decimal("100000000"),
            "cash_savings": Decimal("100000000"),
        },
        Decimal("5000000"),
        savings_split={
            "stocks_vn": Decimal("0.60"),
            "gold": Decimal("0.20"),
            "cash_savings": Decimal("0.20"),
        },
        horizon=10,
        seed=42,
    )
    cone = aggregate_cone(result)

    golden_path = Path(__file__).with_name("golden_mass_affluent_cone.json")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert [
        {"year": p.year, "p10": str(p.p10), "p50": str(p.p50), "p90": str(p.p90)}
        for p in cone[:3]
    ] == golden
    assert Decimal("1.2E+9") <= cone[10].p50 <= Decimal("2.5E+9")
    assert np.isfinite(result).all()


def test_four_wealth_level_fixtures_do_not_raise():
    fixtures = [
        ({"cash_savings": Decimal("8000000"), "stocks_vn": Decimal("4000000")}, Decimal("3000000")),
        ({"stocks_vn": Decimal("60000000"), "crypto": Decimal("15000000"), "cash_savings": Decimal("50000000"), "gold": Decimal("15000000")}, Decimal("10000000")),
        ({"stocks_vn": Decimal("250000000"), "crypto": Decimal("80000000"), "cash_savings": Decimal("100000000"), "gold": Decimal("50000000")}, Decimal("25000000")),
        ({"real_estate_vn": Decimal("1200000000"), "stocks_vn": Decimal("600000000"), "gold": Decimal("200000000"), "cash_savings": Decimal("400000000")}, Decimal("50000000")),
    ]

    for allocation, savings in fixtures:
        result = simulate_portfolio(allocation, savings, savings_split=None, horizon=10, seed=42)
        cone = aggregate_cone(result)
        assert len(cone) == 11
        assert np.isfinite(result).all()


def test_engine_version_is_exported_and_consumed():
    # 4a.2.0 ships the Pareto-aware optimal trajectory: scenarios may select
    # ``savings_only`` instead of always rebalancing to the wealth-tier target.
    assert ENGINE_VERSION == "4a.2.0"
    assert engine_version_for_projection() == ENGINE_VERSION


def test_render_cone_chart_returns_png_bytes_fast():
    from backend.twin.services.twin_chart_service import render_projection_chart

    cone = [
        {"year": 0, "p10": "100000000", "p50": "100000000", "p90": "100000000"},
        {"year": 1, "p10": "95000000", "p50": "112000000", "p90": "135000000"},
        {"year": 2, "p10": "98000000", "p50": "126000000", "p90": "170000000"},
    ]
    png = render_projection_chart(cone, width=400, height=300)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 10_000
