"""Tests for morning report — chart rendering, text building, and orchestration.

The morning report aggregates Phase 3A V2 ``Asset`` rows (``current_value``
+ ``asset_type`` from ``content/asset_categories.yaml``) and renders
labels via ``wealth.asset_types.get_label`` / ``get_icon``. Tests
therefore must use the V2 canonical ``asset_type`` vocabulary
(``stock`` / ``cash`` / ``real_estate`` / ``crypto`` / ``gold`` /
``other``) — V1 plurals like ``stocks`` would miss the YAML lookup
and fall back to the raw key.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.chart_service import ASSET_TYPE_CONFIG, render_donut_chart, _format_vnd
from backend.services.morning_report_service import (
    _build_greeting,
    _build_no_assets_message,
    _build_text_summary,
    build_morning_report,
)


def _make_asset(
    *,
    asset_type: str = "stock",
    name: str = "VNM",
    quantity: float | None = None,
    purchase_price: float | None = None,
    current_price: float | None = None,
):
    """Mock a V2 Asset row.

    V1-style kwargs (quantity / purchase_price / current_price) stay in
    the signature for readable assertions but are translated into V2
    columns the production morning_report code reads:
    ``initial_value`` (cost basis) and ``current_value`` (mark-to-market).
    Pass ``asset_type`` from the V2 vocabulary (``stock``, ``gold``…) so
    YAML label lookups succeed.
    """
    if quantity is not None and purchase_price is not None:
        initial_value = Decimal(str(quantity)) * Decimal(str(purchase_price))
    else:
        initial_value = Decimal(str(purchase_price or 0))

    if quantity is not None and current_price is not None:
        current_value = Decimal(str(quantity)) * Decimal(str(current_price))
    else:
        current_value = Decimal(str(current_price or 0))

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
    asset.extra = None
    asset.created_at = datetime(2026, 1, 1)
    asset.updated_at = datetime(2026, 1, 1)
    asset.deleted_at = None
    return asset


# --- chart_service tests ---

class TestFormatVnd:
    def test_ty(self):
        assert _format_vnd(1_500_000_000) == "1.5 tỷ"

    def test_trieu(self):
        assert _format_vnd(524_300_000) == "524.3 triệu"

    def test_k(self):
        assert _format_vnd(150_000) == "150k"

    def test_small(self):
        assert _format_vnd(500) == "500"

    def test_negative_trieu(self):
        assert _format_vnd(-50_000_000) == "-50.0 triệu"


class TestRenderDonutChart:
    def test_returns_png_bytes(self):
        allocation = {"stocks": 60.0, "gold": 40.0}
        values = {"stocks": 300_000_000, "gold": 200_000_000}
        result = render_donut_chart(
            allocation=allocation,
            allocation_values=values,
            total_value=500_000_000,
        )
        assert isinstance(result, bytes)
        assert len(result) > 0
        # PNG magic bytes
        assert result[:4] == b"\x89PNG"

    def test_with_change_pct(self):
        result = render_donut_chart(
            allocation={"stocks": 100.0},
            allocation_values={"stocks": 100_000_000},
            total_value=100_000_000,
            change_pct=5.3,
        )
        assert result[:4] == b"\x89PNG"

    def test_with_negative_change(self):
        result = render_donut_chart(
            allocation={"crypto": 100.0},
            allocation_values={"crypto": 50_000_000},
            total_value=50_000_000,
            change_pct=-12.5,
        )
        assert result[:4] == b"\x89PNG"

    def test_empty_allocation_returns_placeholder(self):
        result = render_donut_chart(
            allocation={},
            allocation_values={},
            total_value=0,
        )
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_multiple_asset_types(self):
        allocation = {
            "real_estate": 40.0,
            "stocks": 25.0,
            "mutual_fund": 15.0,
            "crypto": 10.0,
            "gold": 10.0,
        }
        values = {
            "real_estate": 2_000_000_000,
            "stocks": 1_250_000_000,
            "mutual_fund": 750_000_000,
            "crypto": 500_000_000,
            "gold": 500_000_000,
        }
        result = render_donut_chart(
            allocation=allocation,
            allocation_values=values,
            total_value=5_000_000_000,
            change_pct=9.6,
            net_worth=5_000_000_000,
            timestamp="07:00 10/04/2026",
        )
        assert result[:4] == b"\x89PNG"

    def test_all_asset_types_have_config(self):
        expected = {"real_estate", "stocks", "mutual_fund", "crypto", "life_insurance", "gold", "cash"}
        assert expected == set(ASSET_TYPE_CONFIG.keys())


# --- morning_report_service tests ---

class TestBuildGreeting:
    def test_contains_date(self):
        greeting = _build_greeting()
        assert "🌅" in greeting
        assert "📅" in greeting
        assert "/" in greeting  # date format DD/MM/YYYY

    def test_contains_weekday(self):
        greeting = _build_greeting()
        weekdays = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        assert any(wd in greeting for wd in weekdays)


class TestBuildNoAssetsMessage:
    def test_encourages_adding_assets(self):
        msg = _build_no_assets_message()
        assert "Thêm tài sản" in msg
        assert "🌅" in msg


class TestBuildTextSummary:
    def test_basic_summary(self):
        text = _build_text_summary(
            allocation_values={"stock": 300_000_000, "gold": 200_000_000},
            allocation_pct={"stock": 60.0, "gold": 40.0},
            total_value=500_000_000,
            change_pct=None,
        )
        assert "💰" in text
        assert "500.0 triệu" in text
        assert "Chứng khoán" in text
        assert "Vàng" in text
        assert "60.0%" in text

    def test_with_positive_change(self):
        text = _build_text_summary(
            allocation_values={"stock": 100_000_000},
            allocation_pct={"stock": 100.0},
            total_value=100_000_000,
            change_pct=9.6,
        )
        assert "↑" in text
        assert "9.6%" in text

    def test_with_negative_change(self):
        text = _build_text_summary(
            allocation_values={"crypto": 50_000_000},
            allocation_pct={"crypto": 100.0},
            total_value=50_000_000,
            change_pct=-3.2,
        )
        assert "↓" in text
        assert "3.2%" in text

    def test_sorted_by_value_desc(self):
        text = _build_text_summary(
            allocation_values={"gold": 100_000_000, "stock": 400_000_000},
            allocation_pct={"gold": 20.0, "stock": 80.0},
            total_value=500_000_000,
            change_pct=None,
        )
        lines = text.split("\n")
        # stocks should appear before gold (higher value)
        stocks_idx = next(i for i, l in enumerate(lines) if "Chứng khoán" in l)
        gold_idx = next(i for i, l in enumerate(lines) if "Vàng" in l)
        assert stocks_idx < gold_idx


class TestBuildMorningReport:
    @pytest.mark.asyncio
    async def test_no_assets_returns_empty(self):
        db = AsyncMock()
        user_id = uuid.uuid4()

        # ``build_morning_report`` calls ``asset_service.get_user_assets``
        # — patch it via the module attribute the service imports.
        with patch(
            "backend.services.morning_report_service.asset_service.get_user_assets",
            return_value=[],
        ):
            chart, text, has_assets = await build_morning_report(db, user_id)

        assert chart is None
        assert text == ""
        assert has_assets is False

    @pytest.mark.asyncio
    async def test_with_assets_returns_chart(self):
        db = AsyncMock()
        user_id = uuid.uuid4()

        assets = [
            _make_asset(asset_type="stock", quantity=100, purchase_price=80000, current_price=90000),
            _make_asset(asset_type="gold", quantity=5, purchase_price=7000000, current_price=7500000),
        ]

        with patch(
            "backend.services.morning_report_service.asset_service.get_user_assets",
            return_value=assets,
        ), patch(
            "backend.services.morning_report_service._get_previous_month_total",
            return_value=None,
        ):
            chart, text, has_assets = await build_morning_report(db, user_id)

        assert has_assets is True
        assert chart is not None
        assert chart[:4] == b"\x89PNG"
        assert "Chứng khoán" in text
        assert "Vàng" in text
