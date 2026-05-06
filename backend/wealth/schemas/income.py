"""Pydantic schemas for ``IncomeStream`` create/update/read flows.

These schemas mediate between three layers:
- The Telegram wizard (writes typed-and-validated input).
- The agent's ``GetIncomeTool`` (reads aggregate stats).
- The eventual REST income router (Phase 1+).

All money fields are ``Decimal`` so monthly aggregations compose
exactly across thousands of rows; the rounded float in
``passive_ratio`` is fine because it's a percentage display value
(0-100) that no other math chains off.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.wealth.income_types import ScheduleType, StreamType


class IncomeStreamCreate(BaseModel):
    """Input for creating a new income stream.

    ``is_passive`` is optional — when omitted, ``IncomeService`` falls
    back to the YAML default for the type (rental/dividend/interest =
    passive, salary/freelance/other = active). Wizard-driven creates
    pass it through unchanged so the user can override the default
    in the unusual case (e.g. "salary" that's mostly bonus).
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: str = Field(..., min_length=1, max_length=200)
    stream_type: StreamType
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="VND", max_length=10)
    schedule_type: ScheduleType
    schedule_day: Optional[int] = Field(default=None, ge=1, le=31)
    schedule_month: Optional[int] = Field(default=None, ge=1, le=12)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    source_asset_id: Optional[uuid.UUID] = None
    # Override flag — let callers force-set passive vs active. None
    # means "derive from YAML default for stream_type".
    is_passive: Optional[bool] = None

    @model_validator(mode="after")
    def _check_lifecycle_dates(self) -> "IncomeStreamCreate":
        """End must follow start. Match ``RentalMetadata`` invariant."""
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date <= self.start_date
        ):
            raise ValueError("end_date must be after start_date")
        return self

    @model_validator(mode="after")
    def _check_schedule_fields(self) -> "IncomeStreamCreate":
        """``schedule_month`` only makes sense for annual streams,
        ``schedule_day`` for monthly. We don't *reject* a stray field
        — the wizard sometimes carries the previously-picked day
        through a schedule change — but downstream code (reminders,
        next-payment computation) will ignore the inapplicable one.

        For now: just zero out the inapplicable field so it doesn't
        leak into the DB and confuse later consumers."""
        sched = (
            self.schedule_type.value
            if isinstance(self.schedule_type, ScheduleType)
            else self.schedule_type
        )
        if sched != "monthly":
            object.__setattr__(self, "schedule_day", None)
        if sched != "annually":
            object.__setattr__(self, "schedule_month", None)
        return self


class IncomeStreamUpdate(BaseModel):
    """Partial update — every field optional. The service overlays
    only the fields that are actually present (``model_dump(
    exclude_unset=True)``)."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    amount: Optional[Decimal] = Field(default=None, gt=0)
    currency: Optional[str] = Field(default=None, max_length=10)
    schedule_type: Optional[ScheduleType] = None
    schedule_day: Optional[int] = Field(default=None, ge=1, le=31)
    schedule_month: Optional[int] = Field(default=None, ge=1, le=12)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    is_passive: Optional[bool] = None


class IncomeBreakdown(BaseModel):
    """Aggregate stats returned by ``get_income_breakdown``.

    Used by the agent tool, the morning briefing (Mass Affluent
    level), and the menu:cashflow:income list view.
    """

    model_config = ConfigDict(use_enum_values=True)

    total_monthly: Decimal
    active_income: Decimal
    passive_income: Decimal
    # ``None`` when total == 0 — tells the formatter to show "Chưa có
    # nguồn thu" instead of a misleading 0%.
    passive_ratio: Optional[float]
    stream_count: int
    # Per-type breakdown for the agent's "thu nhập từ X" follow-ups.
    breakdown_by_type: dict[str, Decimal]


__all__ = [
    "IncomeStreamCreate",
    "IncomeStreamUpdate",
    "IncomeBreakdown",
]
