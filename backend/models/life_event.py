"""Life event SQLAlchemy model — Phase 4B Epic 2.

A life event is a planned milestone (mua nhà, đám cưới, sinh con, học ĐH cho con,
nghỉ hưu sớm, hoặc tuỳ chỉnh) that injects deterministic cashflow shocks into
the Financial Twin's Monte Carlo paths. See ``backend/twin/engine/life_events.py``
for path injection logic and ``backend/life_events/`` for service/presets.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class LifeEventType(str, Enum):
    """Supported life event types. Order matches preset rendering order."""

    BUY_HOUSE = "buy_house"
    WEDDING = "wedding"
    FIRST_CHILD = "first_child"
    CHILD_UNIVERSITY = "child_university"
    EARLY_RETIREMENT = "early_retirement"
    CUSTOM = "custom"


class LifeEvent(Base):
    __tablename__ = "life_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    planned_date: Mapped[date | None] = mapped_column(Date)
    one_time_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    recurring_monthly_delta: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    recurring_duration_months: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (
        Index(
            "life_events_user_active_idx",
            "user_id",
            postgresql_where=text("deleted_at IS NULL AND is_active = TRUE"),
        ),
    )
