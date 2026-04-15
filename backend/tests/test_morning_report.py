"""Tests for morning report — chart rendering, text building, and orchestration."""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.chart_service import ASSET_TYPE_CONFIG, render_donut_chart, _format_vnd
from backend.services.morning_report_service import (
    _build_greeting,
    _build_no_assets_message,
    _build_text_summary,
    build_morning_report,
)


def _make_asset(**kwargs):
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
            allocation_values={"stocks": 300_000_000, "gold": 200_000_000},
            allocation_pct={"stocks": 60.0, "gold": 40.0},
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
            allocation_values={"stocks": 100_000_000},
            allocation_pct={"stocks": 100.0},
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
            allocation_values={"gold": 100_000_000, "stocks": 400_000_000},
            allocation_pct={"gold": 20.0, "stocks": 80.0},
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

        with patch("backend.services.morning_report_service.list_assets", return_value=[]):
            chart, text, has_assets = await build_morning_report(db, user_id)

        assert chart is None
        assert text == ""
        assert has_assets is False

    @pytest.mark.asyncio
    async def test_with_assets_returns_chart(self):
        db = AsyncMock()
        user_id = uuid.uuid4()

        assets = [
            _make_asset(asset_type="stocks", quantity=100, purchase_price=80000, current_price=90000),
            _make_asset(asset_type="gold", quantity=5, purchase_price=7000000, current_price=7500000),
        ]

        with patch("backend.services.morning_report_service.list_assets", return_value=assets), \
             patch("backend.services.morning_report_service._get_previous_month_total", return_value=None):
            chart, text, has_assets = await build_morning_report(db, user_id)

        assert has_assets is True
        assert chart is not None
        assert chart[:4] == b"\x89PNG"
        assert "Chứng khoán" in text
        assert "Vàng" in text
