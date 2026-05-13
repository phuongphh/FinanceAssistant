"""Cashflow forecast snapshot — Phase 4B Epic 3 (Story S16).

One row per user per day: the daily cron job overwrites the current
day's row (via ON CONFLICT on (user_id, forecast_date)) so consumers
always read the latest same-day snapshot.

``monthly_data`` stores a JSON list of MonthlyForecastData objects:
    [
        {
            "month": "2026-11-01",
            "income": "20500000.00",
            "expense": "15300000.00",
            "net": "5200000.00",
            "balance_eom": "32000000.00"
        },
        ...
    ]

Keeping the raw data as JSONB rather than normalised rows makes the
common read path (Mini App fetch + morning briefing) a single-row
lookup with no joins, and allows schema evolution without migrations.

Layer contract: service flushes — caller commits.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

ENGINE_VERSION = "1.0"


class CashflowForecast(Base):
    __tablename__ = "cashflow_forecasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Logical date (not timestamp) so dedup is calendar-day-scoped.
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    horizon_months: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # List of MonthlyForecastData dicts — see module docstring.
    monthly_data: Mapped[list] = mapped_column(JSONB, nullable=False)

    # Pre-computed alert flags so the morning briefing job can read
    # risk without re-running the full forecast.
    low_balance_risk: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    low_balance_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    low_balance_threshold: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    engine_version: Mapped[str] = mapped_column(
        String(20), default=ENGINE_VERSION, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
