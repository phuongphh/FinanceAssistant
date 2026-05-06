"""Unit tests for ``backend.wealth.schemas.rental``.

Schema is small and pure (no DB / network), so tests run fast and
cover:

- Required vs optional fields
- Lease date ordering invariant
- ``net_monthly_yield`` math (including negative when expenses > rent)
- ``annual_yield_pct`` divide-by-zero guard
- ``is_income_active`` only true when status == ``rented``
- JSON round-trip through ``model_dump(mode='json')``
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.wealth.schemas.rental import (
    OccupancyStatus,
    RentalMetadata,
    RentalYieldSummary,
)


class TestRentalMetadataValidation:
    def test_minimal_valid_payload(self):
        m = RentalMetadata(monthly_rent=Decimal("15000000"))
        assert m.monthly_rent == Decimal("15000000")
        # Default vacant — safer than rented (we don't auto-create
        # income flow on the user's behalf without an explicit choice).
        assert m.occupancy_status == OccupancyStatus.VACANT.value
        assert m.monthly_expenses == Decimal("0")
        assert m.deposit_held == Decimal("0")

    def test_zero_rent_rejected(self):
        with pytest.raises(ValueError):
            RentalMetadata(monthly_rent=Decimal("0"))

    def test_negative_rent_rejected(self):
        with pytest.raises(ValueError):
            RentalMetadata(monthly_rent=Decimal("-1"))

    def test_negative_expenses_rejected(self):
        with pytest.raises(ValueError):
            RentalMetadata(
                monthly_rent=Decimal("15000000"),
                monthly_expenses=Decimal("-1"),
            )

    def test_lease_dates_must_be_ordered(self):
        with pytest.raises(ValueError):
            RentalMetadata(
                monthly_rent=Decimal("15000000"),
                lease_start_date=date(2025, 6, 1),
                lease_end_date=date(2025, 1, 1),
            )

    def test_only_start_date_is_fine(self):
        # Skipping end_date is allowed — month-to-month leases.
        m = RentalMetadata(
            monthly_rent=Decimal("15000000"),
            lease_start_date=date(2025, 6, 1),
        )
        assert m.lease_start_date == date(2025, 6, 1)
        assert m.lease_end_date is None

    def test_extra_field_rejected(self):
        # extra='forbid' catches typos in JSON loaded from DB.
        with pytest.raises(ValueError):
            RentalMetadata(
                monthly_rent=Decimal("15000000"),
                wrongly_named_field="oops",
            )


class TestComputedProperties:
    def test_net_monthly_yield_simple(self):
        m = RentalMetadata(
            monthly_rent=Decimal("15000000"),
            monthly_expenses=Decimal("1500000"),
        )
        assert m.net_monthly_yield == Decimal("13500000")

    def test_net_monthly_yield_can_go_negative(self):
        # Heavy renovation period: expenses > rent → user wants to
        # see the loss reflected, not clamped to zero.
        m = RentalMetadata(
            monthly_rent=Decimal("10000000"),
            monthly_expenses=Decimal("12000000"),
        )
        assert m.net_monthly_yield == Decimal("-2000000")

    def test_annual_yield_pct(self):
        m = RentalMetadata(
            monthly_rent=Decimal("15000000"),
            monthly_expenses=Decimal("1500000"),
        )
        # net annual = 13.5tr × 12 = 162tr; / 2.5 tỷ × 100 = 6.48%
        assert m.annual_yield_pct(Decimal("2500000000")) == pytest.approx(6.48)

    def test_annual_yield_pct_zero_value(self):
        m = RentalMetadata(monthly_rent=Decimal("15000000"))
        # Defensive — never crash a briefing.
        assert m.annual_yield_pct(Decimal(0)) == 0.0

    def test_is_income_active_only_when_rented(self):
        m_rented = RentalMetadata(
            monthly_rent=Decimal("15000000"),
            occupancy_status=OccupancyStatus.RENTED,
        )
        m_vacant = RentalMetadata(
            monthly_rent=Decimal("15000000"),
            occupancy_status=OccupancyStatus.VACANT,
        )
        m_self_use = RentalMetadata(
            monthly_rent=Decimal("15000000"),
            occupancy_status=OccupancyStatus.SELF_USE,
        )
        assert m_rented.is_income_active() is True
        assert m_vacant.is_income_active() is False
        assert m_self_use.is_income_active() is False


class TestSerialization:
    def test_round_trip_through_json(self):
        """Mimic what happens in the service: dump for storage in
        JSONB, then re-validate on the way out."""
        original = RentalMetadata(
            monthly_rent=Decimal("15000000"),
            monthly_expenses=Decimal("1500000"),
            occupancy_status=OccupancyStatus.RENTED,
            tenant_name="Anh Tuấn",
            lease_start_date=date(2025, 1, 1),
            lease_end_date=date(2026, 12, 31),
            deposit_held=Decimal("30000000"),
        )
        dumped = original.model_dump(mode="json")
        # Decimal serialised as str → safer than scientific notation.
        assert isinstance(dumped["monthly_rent"], str)
        # Date serialised as ISO string.
        assert dumped["lease_start_date"] == "2025-01-01"
        # Round-trip recovers the same model.
        restored = RentalMetadata.model_validate(dumped)
        assert restored.monthly_rent == original.monthly_rent
        assert restored.lease_start_date == original.lease_start_date


class TestRentalYieldSummary:
    def test_empty_summary_blended_yield_is_none(self):
        s = RentalYieldSummary(
            property_count=0,
            occupied_count=0,
            vacant_count=0,
            self_use_count=0,
            total_monthly_rent=Decimal(0),
            total_monthly_expenses=Decimal(0),
            net_monthly_yield=Decimal(0),
            annual_passive_income=Decimal(0),
            total_property_value=Decimal(0),
            blended_annual_yield_pct=None,
        )
        # Distinguishes "no rentals" from a literal 0% yield.
        assert s.blended_annual_yield_pct is None
