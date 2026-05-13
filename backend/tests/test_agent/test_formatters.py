"""Formatter unit tests — verify text shapes for the five tools.

Formatters are pure: given a Pydantic dump + a user + a style, they
return a string. We assert key substrings rather than full text so
the tests survive copy edits."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from backend.agent.tier2.formatters import (
    format_assets_response,
    format_comparison_response,
    format_market_response,
    format_metric_response,
    format_transactions_response,
)
from backend.intent.wealth_adapt import LevelStyle
from backend.wealth.ladder import WealthLevel


def _style(level=WealthLevel.YOUNG_PROFESSIONAL) -> LevelStyle:
    return LevelStyle(
        level=level,
        net_worth=Decimal("100_000_000"),
        show_percent_change=True,
        show_pnl_pct=True,
        show_allocation_pct=False,
        show_ytd_return=False,
        encouragement=None,
        growth_hint=None,
    )


def _user(name="Hà"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.display_name = name
    return u


class TestAssetsFormatter:
    def test_winners_header_when_positive_filter(self):
        payload = {
            "assets": [
                {"name": "VNM", "ticker": "VNM", "asset_type": "stock",
                 "current_value": "110000000", "gain_pct": 10.0},
                {"name": "NVDA", "ticker": "NVDA", "asset_type": "stock",
                 "current_value": "120000000", "gain_pct": 20.0},
            ],
            "total_value": "230000000",
            "count": 2,
        }
        out = format_assets_response(
            payload, _user(), "mã đang lãi", _style(),
            tool_args={"filter": {"asset_type": "stock", "gain_pct": {"gt": 0}}},
        )
        assert "lãi" in out.lower()
        assert "VNM" in out and "NVDA" in out
        assert "+10.0%" in out
        assert "🟢" in out

    def test_losers_header(self):
        payload = {
            "assets": [
                {"name": "HPG", "ticker": "HPG", "asset_type": "stock",
                 "current_value": "95000000", "gain_pct": -5.0},
            ],
            "total_value": "95000000",
            "count": 1,
        }
        out = format_assets_response(
            payload, _user(), "mã đang lỗ", _style(),
            tool_args={"filter": {"asset_type": "stock", "gain_pct": {"lt": 0}}},
        )
        assert "lỗ" in out.lower()
        assert "🔴" in out
        assert "-5.0%" in out

    def test_top_n_header(self):
        payload = {
            "assets": [
                {"name": "NVDA", "ticker": "NVDA", "asset_type": "stock",
                 "current_value": "120000000", "gain_pct": 20.0},
                {"name": "VNM", "ticker": "VNM", "asset_type": "stock",
                 "current_value": "110000000", "gain_pct": 10.0},
                {"name": "FPT", "ticker": "FPT", "asset_type": "stock",
                 "current_value": "97000000", "gain_pct": -3.0},
            ],
            "total_value": "327000000",
            "count": 3,
        }
        out = format_assets_response(
            payload, _user(), "top 3 mã lãi", _style(),
            tool_args={
                "filter": {"asset_type": "stock"},
                "sort": "gain_pct_desc",
                "limit": 3,
            },
        )
        assert "Top 3" in out

    def test_empty_winners_friendly(self):
        out = format_assets_response(
            {"assets": [], "total_value": "0", "count": 0},
            _user(),
            "mã đang lãi",
            _style(),
            tool_args={"filter": {"gain_pct": {"gt": 0}}},
        )
        assert "chưa có mã nào đang lãi" in out

    def test_empty_assets_overall(self):
        out = format_assets_response(
            {"assets": [], "total_value": "0", "count": 0},
            _user(),
            "tài sản",
            _style(),
            tool_args={},
        )
        assert "/themtaisan" in out


class TestMetricFormatter:
    def test_percent_with_sign(self):
        out = format_metric_response(
            {
                "metric_name": "saving_rate",
                "value": 32.5,
                "unit": "percent",
                "period": "month",
                "context": "Income 30tr / Expense 20tr.",
            },
            _user(),
            _style(),
        )
        assert "Tỷ lệ tiết kiệm" in out
        assert "+32.50%" in out

    def test_vnd_format(self):
        out = format_metric_response(
            {
                "metric_name": "portfolio_total_gain",
                "value": 5_000_000,
                "unit": "vnd",
                "period": "inception",
                "context": None,
            },
            _user(),
            _style(),
        )
        assert "5,000,000đ" in out


class TestComparisonFormatter:
    def test_diff_arrow(self):
        out = format_comparison_response(
            {
                "metric": "expenses",
                "period_a_value": "5000000",
                "period_b_value": "4000000",
                "diff_absolute": "1000000",
                "diff_percent": 25.0,
                "period_a_label": "tháng này",
                "period_b_label": "tháng trước",
            },
            _user(),
            _style(),
        )
        assert "📈" in out
        assert "+25.0%" in out
        assert "Tháng này" in out  # capitalized in output


class TestMarketFormatter:
    def test_price_and_holding(self):
        out = format_market_response(
            {
                "ticker": "VNM",
                "asset_name": "Vinamilk",
                "current_price": "75000",
                "change_pct": 1.2,
                "period": "1d",
                "user_owns": True,
                "user_quantity": 100.0,
                "user_holding_value": "7500000",
                "note": None,
            },
            _user(),
            _style(),
        )
        assert "Vinamilk" in out and "VNM" in out
        assert "+1.20%" in out
        assert "Bạn đang nắm" in out

    def test_no_data(self):
        out = format_market_response(
            {
                "ticker": "ABC",
                "asset_name": None,
                "current_price": "0",
                "change_pct": None,
                "period": "1d",
                "user_owns": False,
                "note": "Chưa có dữ liệu",
            },
            _user(),
            _style(),
        )
        assert "Chưa có dữ liệu" in out


class TestTransactionsFormatter:
    def test_renders_rows_and_total(self):
        from datetime import date
        out = format_transactions_response(
            {
                "transactions": [
                    {"date": date(2026, 5, 3), "merchant": "Starbucks",
                     "category": "food", "amount": "120000", "note": None},
                    {"date": date(2026, 5, 1), "merchant": "Grab",
                     "category": "transport", "amount": "60000", "note": None},
                ],
                "total_amount": "180000",
                "count": 2,
            },
            _user(),
            "chi tuần này",
            _style(),
        )
        assert "Starbucks" in out and "Grab" in out
        assert "180,000đ" in out
