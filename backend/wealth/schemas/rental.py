"""Pydantic schema for the JSONB ``assets.rental_metadata`` column.

The DB column is permissive JSONB; this module is the single source
of truth for what's allowed inside it. Both the wizard handler (when
collecting input) and the rental service (when reading or writing)
go through ``RentalMetadata.model_validate(...)`` so a malformed
metadata row can never reach a user-facing yield calculation.

Money fields are ``Decimal`` so summary aggregations stay exact —
floats would drift on rentals at the tỷ scale.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OccupancyStatus(str, Enum):
    """Three states: ``rented`` (income flowing), ``vacant`` (no
    tenant, no income), ``self_use`` (owner-occupied — also no income
    but distinct because the user might want to flip back to rental
    later without losing the metadata)."""

    RENTED = "rented"
    VACANT = "vacant"
    SELF_USE = "self_use"


class RentalMetadata(BaseModel):
    """Landlord-side rental data attached to a real-estate Asset.

    Stored as JSONB so the column itself never needs a migration.
    All fields except ``monthly_rent`` and ``occupancy_status`` are
    optional — the wizard's "tap to skip extras" flow saves rows
    without lease dates or tenant names.
    """

    # Decimal validate_assignment so threshold logic in the service
    # layer can mutate fields and immediately re-serialise without
    # losing precision through float coercion.
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        use_enum_values=True,
    )

    monthly_rent: Decimal = Field(..., gt=0, description="Tiền thuê (VND)")
    occupancy_status: OccupancyStatus = OccupancyStatus.VACANT
    tenant_name: Optional[str] = Field(default=None, max_length=200)
    lease_start_date: Optional[date] = None
    lease_end_date: Optional[date] = None
    # Default ``Decimal("0")`` covers the common "no recurring expense"
    # case without forcing the user to type 0 in the wizard.
    monthly_expenses: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_held: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def _check_lease_dates(self) -> "RentalMetadata":
        """If both lease dates are given, end must follow start.

        Permissive: missing dates are fine (user skipped them in the
        wizard); we only validate the relationship when the data is
        actually present.
        """
        if (
            self.lease_start_date is not None
            and self.lease_end_date is not None
            and self.lease_end_date <= self.lease_start_date
        ):
            raise ValueError(
                "lease_end_date must be after lease_start_date"
            )
        return self

    @model_validator(mode="after")
    def _check_expenses_not_silly(self) -> "RentalMetadata":
        """Soft sanity check: monthly_expenses ≥ monthly_rent flips
        the rental into a permanent loss, which is almost always a
        wizard typo (e.g. user typed 1.5tr as 15tr). We don't block
        — some users genuinely run loss-making rentals during heavy
        renovation — but the service layer can use this to ask "are
        you sure?" before saving.
        """
        # Actual gating happens in the wizard; this validator just
        # exists as documentation. No-op return.
        return self

    @property
    def net_monthly_yield(self) -> Decimal:
        """Net monthly rental income (rent − expenses).

        Returned as ``Decimal`` so it composes cleanly with other
        Decimal money fields. Vacant / self-use periods produce a
        meaningful number (rent − expenses) too — the *service*
        decides whether to count it toward income; the schema just
        does the math.
        """
        return Decimal(self.monthly_rent) - Decimal(self.monthly_expenses)

    def annual_yield_pct(self, property_value: Decimal | int | float) -> float:
        """Annual net yield as % of property value. ``0.0`` if the
        property has no value (defensive — division-by-zero would
        crash a briefing or summary message)."""
        value = Decimal(str(property_value))
        if value <= 0:
            return 0.0
        annual_net = self.net_monthly_yield * Decimal(12)
        return float(annual_net / value * Decimal(100))

    def is_income_active(self) -> bool:
        """Whether this rental is currently producing income.

        Used by ``RentalService`` to decide if the linked
        ``IncomeStream`` should be active — only ``rented`` state
        does. ``vacant`` and ``self_use`` both pause income. We
        compare against the string value rather than the enum because
        ``use_enum_values=True`` collapses the field to its raw
        string at validation time.
        """
        return self.occupancy_status == OccupancyStatus.RENTED.value


class RentalYieldSummary(BaseModel):
    """Aggregated yield stats for one user's rental portfolio.

    Returned by ``rental_service.get_rental_yield_summary``. All
    money fields are ``Decimal`` so callers can format with
    ``format_money_short`` without precision drift.
    """

    model_config = ConfigDict(use_enum_values=True)

    property_count: int
    occupied_count: int
    vacant_count: int
    self_use_count: int
    total_monthly_rent: Decimal
    total_monthly_expenses: Decimal
    net_monthly_yield: Decimal
    annual_passive_income: Decimal
    # Total current_value of all rental properties (denominator for
    # blended yield). Useful for "tổng giá trị BĐS cho thuê" answers.
    total_property_value: Decimal
    # Blended annual yield % across all rentals. ``None`` when there
    # are no rental properties — distinguishes "no rentals yet" from
    # a literal 0% which would be misleading.
    blended_annual_yield_pct: float | None
