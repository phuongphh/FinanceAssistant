"""Persisted bank savings-rate snapshots."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class BankRateSnapshot(Base):
    __tablename__ = "bank_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tenor_months: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), nullable=False)
    deposit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    snapshot_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("bank_code", "tenor_months", "deposit_type", "snapshot_date", name="uq_bank_rate_snapshot"),
        Index("idx_bank_rates_lookup", "bank_code", "snapshot_date"),
    )
