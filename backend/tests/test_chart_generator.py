"""Unit tests for backend.services.chart_generator."""
import struct
import zlib

import pytest

from backend.services.chart_generator import _empty_chart, generate_portfolio_chart


def _is_png(data: bytes) -> bool:
    """Return True if *data* starts with the PNG magic bytes."""
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Extract (width, height) from a PNG's IHDR chunk."""
    # IHDR is always the first chunk; width/height are at bytes 16-23
    width  = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    return width, height


# ---------------------------------------------------------------------------
# generate_portfolio_chart
# ---------------------------------------------------------------------------

class TestGeneratePortfolioChart:
    def test_returns_png_bytes(self):
        assets = [{"asset_type": "stocks", "value": 10_000_000}]
        result = generate_portfolio_chart(assets)
        assert isinstance(result, bytes)
        assert _is_png(result)

    def test_empty_data_returns_placeholder_png(self):
        result = generate_portfolio_chart([])
        assert isinstance(result, bytes)
        assert _is_png(result)

    def test_zero_value_assets_returns_placeholder_png(self):
        assets = [{"asset_type": "stocks", "value": 0}]
        result = generate_portfolio_chart(assets)
        assert _is_png(result)

    def test_single_asset(self):
        assets = [{"asset_type": "real_estate", "value": 500_000_000}]
        result = generate_portfolio_chart(assets, change_pct=2.5, timestamp="07:00 24/04/2026")
        assert _is_png(result)
        assert len(result) > 1000  # sanity: not a trivially empty file

    def test_many_assets_seven_plus(self):
        assets = [
            {"asset_type": "real_estate",    "value": 500_000_000},
            {"asset_type": "stocks",         "value": 200_000_000},
            {"asset_type": "mutual_fund",    "value": 100_000_000},
            {"asset_type": "crypto",         "value":  50_000_000},
            {"asset_type": "life_insurance", "value":  80_000_000},
            {"asset_type": "gold",           "value":  30_000_000},
            {"asset_type": "cash",           "value":  20_000_000},
            {"asset_type": "bonds",          "value":  15_000_000},  # unknown type
        ]
        result = generate_portfolio_chart(assets, change_pct=-1.2)
        assert _is_png(result)

    def test_unknown_asset_type_handled(self):
        assets = [{"asset_type": "exotic_asset_xyz", "value": 10_000_000}]
        result = generate_portfolio_chart(assets)
        assert _is_png(result)

    def test_change_pct_positive(self):
        assets = [{"asset_type": "stocks", "value": 10_000_000}]
        result = generate_portfolio_chart(assets, change_pct=5.0)
        assert _is_png(result)

    def test_change_pct_negative(self):
        assets = [{"asset_type": "stocks", "value": 10_000_000}]
        result = generate_portfolio_chart(assets, change_pct=-3.7)
        assert _is_png(result)

    def test_change_pct_none(self):
        assets = [{"asset_type": "stocks", "value": 10_000_000}]
        result = generate_portfolio_chart(assets, change_pct=None)
        assert _is_png(result)

    def test_aggregates_duplicate_asset_types(self):
        assets = [
            {"asset_type": "stocks", "value": 6_000_000},
            {"asset_type": "stocks", "value": 4_000_000},
        ]
        result = generate_portfolio_chart(assets)
        assert _is_png(result)

    def test_output_is_reproducibly_sized(self):
        assets = [{"asset_type": "cash", "value": 1_000_000}]
        r1 = generate_portfolio_chart(assets)
        r2 = generate_portfolio_chart(assets)
        # Both renders should be similarly sized (within 5%)
        assert abs(len(r1) - len(r2)) / max(len(r1), len(r2)) < 0.05


# ---------------------------------------------------------------------------
# _empty_chart
# ---------------------------------------------------------------------------

class TestEmptyChart:
    def test_returns_png_bytes(self):
        result = _empty_chart()
        assert isinstance(result, bytes)
        assert _is_png(result)

    def test_reasonable_file_size(self):
        result = _empty_chart()
        assert len(result) > 500  # not empty
        assert len(result) < 5_000_000  # not absurdly large

    def test_valid_png_dimensions(self):
        result = _empty_chart()
        w, h = _png_dimensions(result)
        assert w > 0
        assert h > 0
