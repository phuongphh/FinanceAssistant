"""Tests for income schemas — validation tests."""
import uuid
from datetime import date

from backend.schemas.income import (
    VALID_INCOME_SOURCES,
    VALID_INCOME_TYPES,
    IncomeRecordCreate,
    IncomeSummary,
)
from backend.schemas.portfolio import (
    VALID_ASSET_TYPES,
    PortfolioAssetCreate,
    PortfolioSummary,
)


class TestIncomeRecordCreate:
    def test_valid_creation(self):
        record = IncomeRecordCreate(
            income_type="active",
            source="salary",
            amount=15_000_000,
            period=date(2026, 4, 1),
        )
        assert record.income_type == "active"
        assert record.amount == 15_000_000

    def test_default_period_is_first_of_month(self):
        record = IncomeRecordCreate(
            income_type="passive",
            source="dividend",
            amount=500_000,
        )
        assert record.period.day == 1

    def test_optional_fields(self):
        record = IncomeRecordCreate(
            income_type="passive",
            source="rental",
            asset_id=uuid.uuid4(),
            amount=3_000_000,
            note="Monthly rent from apartment",
        )
        assert record.asset_id is not None
        assert record.note is not None


class TestPortfolioAssetCreate:
    def test_valid_creation(self):
        asset = PortfolioAssetCreate(
            asset_type="stocks",
            name="VNM",
            quantity=100,
            purchase_price=80000,
            current_price=85000,
        )
        assert asset.name == "VNM"
        assert asset.quantity == 100

    def test_minimal_creation(self):
        asset = PortfolioAssetCreate(
            asset_type="real_estate",
            name="Apartment District 7",
        )
        assert asset.quantity is None
        assert asset.purchase_price is None

    def test_with_metadata(self):
        asset = PortfolioAssetCreate(
            asset_type="real_estate",
            name="House",
            metadata={"address": "123 ABC", "area_sqm": 80},
        )
        assert asset.metadata["area_sqm"] == 80


class TestIncomeSummary:
    def test_passive_ratio_calculation(self):
        summary = IncomeSummary(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 1),
            total_active=10_000_000,
            total_passive=5_000_000,
            total=15_000_000,
            passive_ratio=33.33,
            by_source={"salary": 10_000_000, "dividend": 5_000_000},
        )
        assert summary.passive_ratio == 33.33

    def test_zero_income(self):
        summary = IncomeSummary(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 1),
            total_active=0,
            total_passive=0,
            total=0,
            passive_ratio=None,
            by_source={},
        )
        assert summary.passive_ratio is None


class TestPortfolioSummary:
    def test_summary_structure(self):
        summary = PortfolioSummary(
            total_market_value=100_000_000,
            total_cost=80_000_000,
            total_pnl=20_000_000,
            total_pnl_pct=25.0,
            allocation={"stocks": 60.0, "gold": 40.0},
            asset_count=5,
        )
        assert summary.total_pnl_pct == 25.0
        assert summary.allocation["stocks"] == 60.0


class TestValidConstants:
    def test_asset_types_defined(self):
        assert len(VALID_ASSET_TYPES) == 6
        assert "stocks" in VALID_ASSET_TYPES
        assert "crypto" in VALID_ASSET_TYPES

    def test_income_types_defined(self):
        assert "active" in VALID_INCOME_TYPES
        assert "passive" in VALID_INCOME_TYPES

    def test_income_sources_defined(self):
        assert "salary" in VALID_INCOME_SOURCES
        assert "dividend" in VALID_INCOME_SOURCES
        assert "rental" in VALID_INCOME_SOURCES
