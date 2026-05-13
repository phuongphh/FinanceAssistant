"""Tests for portfolio_service — unit tests for P&L computation and enrichment.

The Phase 3A asset migration moved storage from V1's
(quantity, purchase_price, current_price) triple into the V2 ``Asset``
shape (``initial_value``, ``current_value``, ``extra`` JSONB). The
public V1 API still expresses inputs/outputs in V1 terms — that's
``portfolio_service``'s whole job — but every helper in the service
reads the V2 columns directly.

Tests therefore mock the **V2 surface** (current_value, initial_value,
extra) and use a small ``_make_asset`` helper that accepts V1-style
kwargs purely for readability and converts them. This mirrors what a
real V2 ``Asset`` row looks like after ``portfolio_service.create_asset``
has stored it.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from backend.services.portfolio_service import (
    _compute_asset_fields,
    enrich_asset_response,
)


def _make_asset(
    *,
    quantity: float | None = None,
    purchase_price: float | None = None,
    current_price: float | None = None,
    metadata: dict | None = None,
    asset_type: str = "stocks",
    name: str = "VNM",
):
    """Create a MagicMock that quacks like the V2 Asset model.

    V1-shaped kwargs (quantity / purchase_price / current_price /
    metadata) are translated to the V2 columns the real service code
    reads:

        initial_value  := quantity × purchase_price (or purchase_price
                          alone if no quantity, else 0)
        current_value  := quantity × current_price (or current_price
                          alone, falling back to initial_value)
        extra          := {quantity, avg_price, **metadata} — exactly
                          what ``portfolio_service.create_asset`` writes

    Pass V1 kwargs only; the helper hides the V2 plumbing so the
    assertions stay readable.
    """
    if quantity is not None and purchase_price is not None:
        initial_value = Decimal(str(quantity)) * Decimal(str(purchase_price))
    elif purchase_price is not None:
        initial_value = Decimal(str(purchase_price))
    else:
        initial_value = None

    if quantity is not None and current_price is not None:
        current_value = Decimal(str(quantity)) * Decimal(str(current_price))
    elif current_price is not None:
        current_value = Decimal(str(current_price))
    else:
        current_value = None

    extra: dict = {}
    if quantity is not None:
        extra["quantity"] = quantity
    if purchase_price is not None:
        extra["avg_price"] = purchase_price
    if metadata:
        extra.update(metadata)

    asset = MagicMock(spec_set=[
        "id", "user_id", "asset_type", "name",
        "initial_value", "current_value", "extra",
        "created_at", "updated_at", "deleted_at",
    ])
    asset.id = uuid.uuid4()
    asset.user_id = uuid.uuid4()
    asset.asset_type = asset_type
    asset.name = name
    asset.initial_value = initial_value
    asset.current_value = current_value
    asset.extra = extra or None
    asset.created_at = datetime(2026, 1, 1)
    asset.updated_at = datetime(2026, 1, 1)
    asset.deleted_at = None
    return asset


class TestComputeAssetFields:
    def test_all_none_when_no_data(self):
        asset = _make_asset()
        result = _compute_asset_fields(asset)
        # No initial_value / current_value → no derivation possible.
        assert result["market_value"] == 0
        assert result["unrealized_pnl"] == 0
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
        # Zero-cost basis means percentage is undefined — guard against
        # division-by-zero turning into a misleading 0% or +inf.
        assert result["unrealized_pnl_pct"] is None

    def test_current_price_only_stored_as_unit_value(self):
        # Only current_price is set → V2 stores it as current_value
        # (no quantity multiplier). Production code never produces such
        # rows (asset_service.create_asset always pairs quantity with
        # price), but the helper must still return without crashing.
        asset = _make_asset(current_price=80000)
        result = _compute_asset_fields(asset)
        assert result["market_value"] == 80_000


class TestEnrichAssetResponse:
    def test_includes_computed_fields(self):
        asset = _make_asset(quantity=10, purchase_price=50000, current_price=60000)
        resp = enrich_asset_response(asset)
        assert resp["market_value"] == 600_000
        assert resp["unrealized_pnl"] == 100_000
        assert resp["unrealized_pnl_pct"] == 20.0
        assert resp["name"] == "VNM"
        assert resp["asset_type"] == "stocks"
        # V1 shape preserved: quantity / purchase_price / current_price
        # are reconstructed from extra + value columns.
        assert resp["quantity"] == 10
        assert resp["purchase_price"] == 50000
        assert resp["current_price"] == 60000

    def test_metadata_mapped_correctly(self):
        # Per-type metadata sits alongside quantity/avg_price in extra
        # but is exposed under the "metadata" key by the V1 response
        # shape (quantity/avg_price are filtered out).
        asset = _make_asset(metadata={"exchange": "HOSE"})
        resp = enrich_asset_response(asset)
        assert resp["metadata"] == {"exchange": "HOSE"}

    def test_none_metadata(self):
        asset = _make_asset()
        resp = enrich_asset_response(asset)
        assert resp["metadata"] is None
