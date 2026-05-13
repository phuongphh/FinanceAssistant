"""Unit tests for Phase 3A wealth models + asset_types YAML loader.

These don't hit the DB — they verify the helper properties (gain/loss
math) and that the YAML is valid + complete for all 6 asset types
defined in the AssetType enum.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.wealth.asset_types import (
    AssetType,
    get_asset_config,
    get_icon,
    get_label,
    get_subtypes,
    load_asset_categories,
)
from backend.wealth.models.asset import Asset


class TestAssetGainLoss:
    def test_gain_when_current_above_initial(self):
        a = Asset(
            initial_value=Decimal("100_000_000"),
            current_value=Decimal("120_000_000"),
        )
        assert a.gain_loss == Decimal("20_000_000")
        assert a.gain_loss_pct == 20.0

    def test_loss_when_current_below_initial(self):
        a = Asset(
            initial_value=Decimal("50_000_000"),
            current_value=Decimal("40_000_000"),
        )
        assert a.gain_loss == Decimal("-10_000_000")
        assert a.gain_loss_pct == -20.0

    def test_zero_initial_returns_none_pct(self):
        a = Asset(initial_value=Decimal("0"), current_value=Decimal("100_000"))
        assert a.gain_loss == Decimal("100_000")
        assert a.gain_loss_pct is None


class TestAssetCategoriesYAML:
    def test_yaml_loads(self):
        cfg = load_asset_categories()
        assert "asset_types" in cfg

    def test_all_enum_types_present(self):
        cfg = load_asset_categories()
        types = cfg["asset_types"]
        for member in AssetType:
            assert member.value in types, f"missing {member.value} in YAML"

    def test_each_type_has_icon_and_label(self):
        for member in AssetType:
            assert get_icon(member.value)
            assert get_label(member.value)

    def test_subtypes_returned_as_dict(self):
        subs = get_subtypes("cash")
        assert isinstance(subs, dict)
        assert "bank_savings" in subs
        assert subs["bank_savings"] == "Tiết kiệm ngân hàng"

    def test_unknown_type_safe_defaults(self):
        assert get_asset_config("nonexistent") == {}
        assert get_subtypes("nonexistent") == {}
        assert get_icon("nonexistent") == "📌"

    def test_real_estate_excludes_rental_subtype(self):
        # Rental (Case B) is intentionally Phase 4 — must not leak in.
        subs = get_subtypes("real_estate")
        assert "rental" not in subs
        assert "house_primary" in subs
        assert "land" in subs


@pytest.mark.parametrize(
    "asset_type,expected_icon",
    [
        ("cash", "💵"),
        ("stock", "📈"),
        ("real_estate", "🏠"),
        ("crypto", "₿"),
        ("gold", "🥇"),
        ("other", "📦"),
    ],
)
def test_icons_match_spec(asset_type, expected_icon):
    assert get_icon(asset_type) == expected_icon
