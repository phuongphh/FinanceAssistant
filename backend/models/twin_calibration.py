"""Twin prediction-vs-actual snapshot log (Phase 4.1, Story B.2).

Each time a user opens their Twin, the calibration service logs three
rows (horizon 7/30/90 days). A daily worker fills ``actual_vnd`` when
the horizon hits and computes ``within_band``. The Twin view reads
hit-rate from this table for the honest "Bé Tiền đoán đúng 7/9 lần"
section.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


HORIZONS_DAYS: tuple[int, ...] = (7, 30, 90)


class TwinCalibrationSnapshot(Base):
    __tablename__ = "twin_calibration_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    p10_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    p50_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    p90_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    actual_vnd: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    actual_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    within_band: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
