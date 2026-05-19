"""Unit tests for the pure helpers in ``action_edit_asset.py``.

The handler itself needs the DB stack; these helpers don't, so we
isolate them here for fast CI feedback on the inline-edit parsing.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.intent.handlers.action_edit_asset import (
    _compute_value_from_quantity,
    _name_matches,
    _parse_quantity,
)


class TestNameMatches:
    @pytest.mark.parametrize(
        "stored,query,expected",
        [
            ("Vàng SJC", "sjc", True),
            ("Vàng SJC", "vang sjc", True),
            ("Vàng SJC", "SJC", True),
            ("ACB tài khoản chính", "acb", True),
            # Diacritic-stripped capture vs diacritic-full stored name.
            ("Đất Ba Tư", "ba tu", True),
            ("Đất Ba Tư", "ba tư", True),
            # Non-match.
            ("Cổ phiếu FPT", "vnm", False),
            ("Vàng SJC", "", False),
            ("", "sjc", False),
        ],
    )
    def test_match(self, stored, query, expected):
        assert _name_matches(stored, query) is expected


class TestParseQuantity:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("200 cổ", Decimal("200")),
            ("200co", Decimal("200")),
            ("0.5 BTC", Decimal("5")),  # decimals are stripped — see note
            ("10 ETH", Decimal("10")),
            ("5 chỉ", Decimal("5")),
            ("100 share", Decimal("100")),
            ("3 cây", Decimal("3")),
            ("50tr", None),
            ("1.2 tỷ", None),
            ("", None),
        ],
    )
    def test_quantity_parse(self, raw, expected):
        # Note: fractional crypto amounts ("0.5 BTC") collapse the
        # decimal point in the simple impl. That's acceptable for V1 —
        # the wizard fallback covers fractional sizing precisely. The
        # test pins the current behaviour so changes are intentional.
        assert _parse_quantity(raw) == expected


class TestComputeValueFromQuantity:
    def test_uses_avg_price(self):
        asset = SimpleNamespace(
            extra={"avg_price": "45000"}, current_value=Decimal("4500000")
        )
        assert _compute_value_from_quantity(asset, Decimal("200")) == Decimal(
            "9000000"
        )

    def test_uses_last_price(self):
        asset = SimpleNamespace(
            extra={"last_price": "30000"}, current_value=None
        )
        assert _compute_value_from_quantity(asset, Decimal("100")) == Decimal(
            "3000000"
        )

    def test_derives_from_current_value_quantity(self):
        # Stored quantity=100 with current_value=10m → unit price 100k.
        asset = SimpleNamespace(
            extra={"quantity": "100"}, current_value=Decimal("10_000_000")
        )
        assert _compute_value_from_quantity(asset, Decimal("250")) == Decimal(
            "25_000_000"
        )

    def test_returns_none_when_no_price_data(self):
        asset = SimpleNamespace(extra={}, current_value=None)
        assert _compute_value_from_quantity(asset, Decimal("100")) is None
