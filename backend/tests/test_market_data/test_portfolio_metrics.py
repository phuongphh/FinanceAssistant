from __future__ import annotations

from decimal import Decimal

from backend.market_data.analytics.portfolio_metrics import compute_diversification_score


def test_diversification_score_good_for_balanced_portfolio():
    result = compute_diversification_score([
        {"asset_type": "stock", "value": Decimal("40")},
        {"asset_type": "cash", "value": Decimal("30")},
        {"asset_type": "gold", "value": Decimal("20")},
        {"asset_type": "crypto", "value": Decimal("10")},
    ])

    assert result["score"] >= 70
    assert result["label"] == "Tốt"


def test_diversification_score_weak_for_single_asset():
    result = compute_diversification_score([{"asset_type": "stock", "value": Decimal("100")}])

    assert result["score"] < 40
    assert result["label"] == "Yếu"
