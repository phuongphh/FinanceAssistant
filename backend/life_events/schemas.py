"""Pydantic schemas for the life-events module.

Edge-of-system validation: the SQLAlchemy ``LifeEvent`` model trusts these
shapes upstream, so any user input (Telegram wizard, Mini App POST) must
flow through ``LifeEventCreate`` / ``LifeEventUpdate`` before reaching the
service layer.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.life_event import LifeEventType


_TITLE_MAX = 200
_NOTES_MAX = 2000
# Sanity bounds keep typos from injecting absurd cashflows into MC paths.
_MAX_ONE_TIME = Decimal("100000000000")          # 100 tỷ VND
_MAX_MONTHLY = Decimal("1000000000")             # 1 tỷ VND
_MIN_MONTHLY = Decimal("-1000000000")
_MAX_DURATION_MONTHS = 600                       # 50 năm


class LifeEventBase(BaseModel):
    event_type: LifeEventType
    title: str | None = Field(default=None, max_length=_TITLE_MAX)
    planned_date: date | None = None
    one_time_cost: Decimal | None = Field(default=None, ge=0, le=_MAX_ONE_TIME)
    recurring_monthly_delta: Decimal | None = Field(
        default=None, ge=_MIN_MONTHLY, le=_MAX_MONTHLY
    )
    recurring_duration_months: int | None = Field(
        default=None, ge=0, le=_MAX_DURATION_MONTHS
    )
    notes: str | None = Field(default=None, max_length=_NOTES_MAX)

    @field_validator("recurring_duration_months")
    @classmethod
    def _zero_duration_means_none(cls, v: int | None) -> int | None:
        # 0 months would be ambiguous (apply once? never?). Normalize to None.
        if v == 0:
            return None
        return v


class LifeEventCreate(LifeEventBase):
    """Body for POST /api/v1/life-events and Telegram add-flow finalization."""


class LifeEventUpdate(BaseModel):
    """PATCH body. All fields optional; explicit ``None`` clears the field."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=_TITLE_MAX)
    planned_date: date | None = None
    one_time_cost: Decimal | None = Field(default=None, ge=0, le=_MAX_ONE_TIME)
    recurring_monthly_delta: Decimal | None = Field(
        default=None, ge=_MIN_MONTHLY, le=_MAX_MONTHLY
    )
    recurring_duration_months: int | None = Field(
        default=None, ge=0, le=_MAX_DURATION_MONTHS
    )
    notes: str | None = Field(default=None, max_length=_NOTES_MAX)
    is_active: bool | None = None


class LifeEventRead(LifeEventBase):
    """Wire format returned to Mini App + Telegram."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LifeEventImpact(BaseModel):
    """Per-event deterministic impact summary for UI.

    ``year_deltas`` is the year-by-year cumulative cashflow shift applied to
    every MC path for this event. Negative means the event drags net worth
    down (mortgage, mua nhà…); positive means it lifts it (rare — e.g. an
    inheritance modelled as a positive one_time_cost). The Mini App can sum
    deltas across selected events without re-running MC.
    """

    event_id: uuid.UUID
    event_type: LifeEventType
    title: str | None = None
    planned_year: int | None = None
    one_time_cost: Decimal = Decimal("0")
    recurring_total_cost: Decimal = Decimal("0")
    year_deltas: list[Decimal] = Field(default_factory=list)
