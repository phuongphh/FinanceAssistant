"""Unit tests for ``IncomeStream.monthly_equivalent`` + the YAML
loader.

The model property is the single source of truth for schedule-to-
monthly conversion — everywhere else (briefing, threshold service,
agent tool) reads through it. So one focused test file pins down
the math.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.wealth.income_types import (
    ScheduleType,
    StreamType,
    all_user_facing_types,
    is_passive_default,
    typical_schedule,
)
from backend.wealth.models.income_stream import IncomeStream


def _make(schedule_type: str, amount: str) -> IncomeStream:
    s = IncomeStream()
    s.amount = Decimal(amount)
    s.schedule_type = schedule_type
    return s


class TestMonthlyEquivalent:
    def test_monthly_passes_through(self):
        s = _make("monthly", "30000000")
        assert s.monthly_equivalent == Decimal("30000000")

    def test_quarterly_divides_by_three(self):
        s = _make("quarterly", "9000000")
        assert s.monthly_equivalent == Decimal("3000000")

    def test_annually_divides_by_twelve(self):
        s = _make("annually", "12000000")
        assert s.monthly_equivalent == Decimal("1000000")

    def test_ad_hoc_uses_amount_as_placeholder(self):
        """Spec: ad-hoc should average over 6 months of receipts.
        Until that history exists, treat ``amount`` as the user's
        own monthly estimate. This test pins down the placeholder so
        a future change is intentional, not accidental.
        """
        s = _make("ad_hoc", "5000000")
        assert s.monthly_equivalent == Decimal("5000000")

    def test_unknown_schedule_falls_through(self):
        """Defensive: an unknown schedule (typo, future enum) should
        return ``amount`` rather than crash. Aggregations stay
        correct on the headline number; the dev fixes the typo
        in the next deploy."""
        s = _make("yearly", "12000000")  # typo
        assert s.monthly_equivalent == Decimal("12000000")

    def test_zero_amount_returns_zero(self):
        s = _make("monthly", "0")
        assert s.monthly_equivalent == Decimal(0)


class TestIncomeTypesYaml:
    def test_all_six_types_loadable(self):
        for t in StreamType:
            from backend.wealth.income_types import get_label
            assert get_label(t.value) != t.value, (
                f"YAML missing label for {t.value}"
            )

    def test_passive_defaults_match_spec(self):
        # Per spec § 1.2 income type table.
        assert is_passive_default("salary") is False
        assert is_passive_default("freelance") is False
        assert is_passive_default("dividend") is True
        assert is_passive_default("rental") is True
        assert is_passive_default("interest") is True
        assert is_passive_default("other") is False

    def test_typical_schedules_match_spec(self):
        assert typical_schedule("salary") == "monthly"
        assert typical_schedule("freelance") == "ad_hoc"
        assert typical_schedule("dividend") == "annually"
        assert typical_schedule("rental") == "monthly"
        assert typical_schedule("interest") == "monthly"
        assert typical_schedule("other") == "ad_hoc"

    def test_rental_is_auto_linked_and_hidden_from_picker(self):
        """Rental streams come from the asset wizard, not the income
        wizard — picker shouldn't offer it (would create a duplicate)."""
        types = all_user_facing_types()
        assert "rental" not in types
        # All other types still offered.
        assert set(types) == {"salary", "freelance", "dividend", "interest", "other"}

    def test_unknown_type_returns_safe_defaults(self):
        from backend.wealth.income_types import get_icon, get_label
        assert get_label("nonsense") == "nonsense"
        assert get_icon("nonsense") == "💰"
        assert is_passive_default("nonsense") is False


class TestSchemaValidator:
    def test_zeros_out_inapplicable_schedule_fields(self):
        from backend.wealth.schemas.income import IncomeStreamCreate

        m = IncomeStreamCreate(
            name="Bonus",
            stream_type=StreamType.OTHER,
            amount=Decimal("1000000"),
            schedule_type=ScheduleType.AD_HOC,
            schedule_day=15,        # nonsense for ad_hoc
            schedule_month=6,       # nonsense for ad_hoc
        )
        assert m.schedule_day is None
        assert m.schedule_month is None

    def test_lease_dates_must_be_ordered(self):
        from datetime import date
        from backend.wealth.schemas.income import IncomeStreamCreate

        with pytest.raises(ValueError):
            IncomeStreamCreate(
                name="x",
                stream_type=StreamType.SALARY,
                amount=Decimal(1),
                schedule_type=ScheduleType.MONTHLY,
                start_date=date(2025, 6, 1),
                end_date=date(2025, 1, 1),
            )

    def test_negative_amount_rejected(self):
        from backend.wealth.schemas.income import IncomeStreamCreate

        with pytest.raises(ValueError):
            IncomeStreamCreate(
                name="x",
                stream_type=StreamType.SALARY,
                amount=Decimal("-1"),
                schedule_type=ScheduleType.MONTHLY,
            )
