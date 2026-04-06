"""Tests for portfolio_service — unit tests for P&L computation and enrichment."""
import uuid
from datetime import datetime
from unittest.mock import MagicMock

from backend.services.portfolio_service import _compute_asset_fields, enrich_asset_response


def _make_asset(**kwargs):
    """Create a mock PortfolioAsset with given fields."""
    defaults = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "asset_type": "stocks",
        "name": "VNM",
        "quantity": None,
        "purchase_price": None,
        "current_price": None,
        "metadata_": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
        "deleted_at": None,
    }
    defaults.update(kwargs)
    asset = MagicMock()
    for k, v in defaults.items():
        setattr(asset, k, v)
    return asset


class TestComputeAssetFields:
    def test_all_none_when_no_data(self):
        asset = _make_asset()
        result = _compute_asset_fields(asset)
        assert result["market_value"] is None
        assert result["unrealized_pnl"] is None
        assert result["unrealized_pnl_pct"] is None

    def test_market_value_calculated(self):
        asset = _make_asset(quantity=100, current_price=85000)
        result = _compute_asset_fields(asset)
        assert result["market_value"] == 8_500_000

    def test_pnl_positive(self):
        asset = _make_asset(quantity=100, purchase_price=80000, current_price=90000)
        result = _compute_asset_fields(asset)
        assert result["market_value"] == 9_000_000
        assert result["unrealized_pnl"] == 1_000_000
        assert result["unrealized_pnl_pct"] == 12.5

    def test_pnl_negative(self):
        asset = _make_asset(quantity=50, purchase_price=100000, current_price=80000)
        result = _compute_asset_fields(asset)
        assert result["unrealized_pnl"] == -1_000_000
        assert result["unrealized_pnl_pct"] == -20.0

    def test_pnl_zero_cost(self):
        asset = _make_asset(quantity=10, purchase_price=0, current_price=50000)
        result = _compute_asset_fields(asset)
        assert result["market_value"] == 500_000
        assert result["unrealized_pnl"] == 500_000
        assert result["unrealized_pnl_pct"] is None

    def test_no_quantity_no_market_value(self):
        asset = _make_asset(current_price=80000)
        result = _compute_asset_fields(asset)
        assert result["market_value"] is None


class TestEnrichAssetResponse:
    def test_includes_computed_fields(self):
        asset = _make_asset(quantity=10, purchase_price=50000, current_price=60000)
        resp = enrich_asset_response(asset)
        assert resp["market_value"] == 600_000
        assert resp["unrealized_pnl"] == 100_000
        assert resp["unrealized_pnl_pct"] == 20.0
        assert resp["name"] == "VNM"
        assert resp["asset_type"] == "stocks"

    def test_metadata_mapped_correctly(self):
        asset = _make_asset(metadata_={"exchange": "HOSE"})
        resp = enrich_asset_response(asset)
        assert resp["metadata"] == {"exchange": "HOSE"}

    def test_none_metadata(self):
        asset = _make_asset()
        resp = enrich_asset_response(asset)
        assert resp["metadata"] is None
