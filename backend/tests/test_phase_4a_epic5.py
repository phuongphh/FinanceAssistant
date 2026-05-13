from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.bot.handlers.twin_handler import send_twin_compare_optimal
from backend.tests._fakes.notifier import FakeNotifier
from backend.twin.allocation.target_allocation import (
    get_allocation_disclaimer,
    get_target_allocation,
    top_rebalance_deltas,
)
from backend.twin.engine.monte_carlo import simulate_portfolio
from backend.twin.engine.optimal_trajectory import simulate_optimal
from backend.wealth.ladder import WealthLevel


@dataclass
class ProjectionStub:
    scenario: str
    monthly_savings: Decimal
    allocation_snapshot: dict[str, str]
    cone_data: list[dict[str, str | int]]
    base_net_worth: Decimal = Decimal("500000000")


def test_target_allocations_cover_four_levels_and_sum_to_one():
    for level in WealthLevel:
        target = get_target_allocation(level)
        assert target
        assert abs(sum(target.values()) - 1.0) <= 0.001

    assert get_target_allocation("Khởi Đầu")["cash_savings"] == 0.65
    assert get_target_allocation("Trung Lưu Vững")["real_estate_vn"] == 0.15
    assert "không phải lời khuyên đầu tư" in get_allocation_disclaimer()


def test_simulate_optimal_reuses_portfolio_shape_and_boosts_mass_affluent():
    portfolio = {
        "stocks_vn": Decimal("300000000"),
        "gold": Decimal("100000000"),
        "cash_savings": Decimal("100000000"),
    }
    current = simulate_portfolio(
        portfolio,
        Decimal("15000000"),
        savings_split={
            "stocks_vn": Decimal("0.6"),
            "gold": Decimal("0.2"),
            "cash_savings": Decimal("0.2"),
        },
        horizon=10,
        paths=1000,
        seed=42,
    )
    optimal = simulate_optimal(
        portfolio,
        WealthLevel.MASS_AFFLUENT,
        10,
        monthly_savings=Decimal("15000000"),
        paths=1000,
        seed=42,
    )

    assert optimal.shape == current.shape == (1000, 11)
    assert optimal[:, 0].mean() == pytest.approx(500_000_000, abs=5)
    assert optimal[:, 10].mean() > current[:, 10].mean()


def test_top_rebalance_deltas_returns_largest_actionable_gaps():
    deltas = top_rebalance_deltas(
        {"crypto": "0.30", "cash_savings": "0.10", "stocks_vn": "0.60"},
        {
            "crypto": 0.05,
            "cash_savings": 0.15,
            "stocks_vn": 0.35,
            "gold": 0.15,
            "real_estate_vn": 0.15,
        },
        base_net_worth=Decimal("500000000"),
        limit=2,
    )

    assert [delta.asset_class for delta in deltas] == ["crypto", "stocks_vn"]
    assert deltas[0].amount_delta == Decimal("-125000000")


@pytest.mark.asyncio
async def test_compare_optimal_handler_sends_dual_cone_caption_with_actions():
    user = SimpleNamespace(id=uuid.uuid4(), display_name="An")
    current = ProjectionStub(
        scenario="current",
        monthly_savings=Decimal("15000000"),
        allocation_snapshot={
            "stocks_vn": "0.60",
            "gold": "0.20",
            "cash_savings": "0.20",
        },
        cone_data=[
            {"year": 0, "p10": "500000000", "p50": "500000000", "p90": "500000000"},
            {"year": 10, "p10": "1200000000", "p50": "1800000000", "p90": "2600000000"},
        ],
    )
    optimal = ProjectionStub(
        scenario="optimal",
        monthly_savings=Decimal("16500000"),
        allocation_snapshot={
            "stocks_vn": "0.35",
            "stocks_global": "0.15",
            "crypto": "0.05",
            "gold": "0.15",
            "cash_savings": "0.15",
            "real_estate_vn": "0.15",
        },
        cone_data=[
            {"year": 0, "p10": "500000000", "p50": "500000000", "p90": "500000000"},
            {"year": 10, "p10": "1500000000", "p50": "2400000000", "p90": "3600000000"},
        ],
    )

    async def fake_latest(db, user_id, scenario=None):
        return current if scenario == "current" else optimal

    notifier = FakeNotifier()
    with (
        patch(
            "backend.bot.handlers.twin_handler.twin_query_service.get_latest_projection",
            fake_latest,
        ),
        patch(
            "backend.bot.handlers.twin_handler.render_projection_chart",
            return_value=b"png-bytes",
        ),
    ):
        await send_twin_compare_optimal(
            SimpleNamespace(), chat_id=123, user=user, notifier=notifier
        )

    assert len(notifier.photos) == 1
    photo = notifier.photos[0]
    assert photo.photo == b"png-bytes"
    assert "1.8 tỷ → 2.4 tỷ (+33%)" in photo.caption
    assert "15tr/tháng → 16.5tr/tháng" in photo.caption
    assert "không phải lời khuyên đầu tư" in photo.caption
