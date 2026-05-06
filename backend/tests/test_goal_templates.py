"""Tests for ``backend.services.goal_templates`` (Phase 3.8 Epic 5).

Locks down the YAML contract — all 7 spec templates exist, each
with the required fields, and the lookup helpers fall back safely
on unknown ids. Mirrors the asset/income type loader test patterns.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services import goal_templates


def setup_module(module):
    # Test module loads templates fresh — spec § P3.8-S13 lists 7
    # templates exactly. Cache is per-process; no need to reset.
    goal_templates.list_templates.cache_clear()
    goal_templates._load_raw.cache_clear()


class TestListTemplates:
    def test_seven_templates_exist(self):
        """Spec § P3.8-S13: exactly 7 templates."""
        templates = goal_templates.list_templates()
        assert len(templates) == 7

    def test_all_spec_ids_present(self):
        """Each spec id must show up — protects against accidental
        renames."""
        ids = {t.id for t in goal_templates.list_templates()}
        assert ids == {
            "buy_car", "buy_house", "travel", "retirement",
            "education", "wedding", "emergency_fund",
        }

    def test_each_template_has_required_fields(self):
        for t in goal_templates.list_templates():
            assert t.name, f"missing name for {t.id}"
            assert t.icon, f"missing icon for {t.id}"
            assert t.category, f"missing category for {t.id}"
            assert isinstance(t.min_amount, Decimal)
            assert isinstance(t.max_amount, Decimal)
            assert t.min_amount > 0
            assert t.max_amount >= t.min_amount
            assert t.min_months > 0
            assert t.max_months >= t.min_months

    def test_buy_car_amounts_match_spec(self):
        """Spec range: 200tr - 1.5 tỷ. Pinning so a YAML edit doesn't
        silently change the wizard's example range."""
        car = goal_templates.get_template("buy_car")
        assert car is not None
        assert car.min_amount == Decimal("200000000")
        assert car.max_amount == Decimal("1500000000")
        assert car.min_months == 12
        assert car.max_months == 60

    def test_emergency_fund_has_description(self):
        ef = goal_templates.get_template("emergency_fund")
        assert ef is not None
        assert ef.description is not None
        assert "6 tháng" in ef.description


class TestLookupHelpers:
    def test_get_template_unknown_returns_none(self):
        """Don't throw on unknown ids — caller branches on None
        (e.g. legacy goal row whose template was removed from YAML)."""
        assert goal_templates.get_template("nonexistent") is None

    def test_get_icon_falls_back_safely(self):
        # Known.
        assert goal_templates.get_icon("buy_car") == "🚗"
        # Unknown / null — fallback to generic 🎯.
        assert goal_templates.get_icon(None) == "🎯"
        assert goal_templates.get_icon("custom") == "🎯"
