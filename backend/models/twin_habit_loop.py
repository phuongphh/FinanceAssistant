from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class TwinRecomputeLog(Base):
    """Latency + notification audit log for on-demand Twin recomputes."""

    __tablename__ = "twin_recompute_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    queue_ms: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    compute_ms: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    notify_ms: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    total_ms: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    delta_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), server_default=text("0"), nullable=False)
    delta_absolute_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 2), server_default=text("0"), nullable=False)
    notified_bool: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"), nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)

    __table_args__ = (
        Index("idx_twin_recompute_user_created", "user_id", "created_at"),
        Index("idx_twin_recompute_event", "event_id"),
    )


class TwinDeltaThresholdConfig(Base):
    """Operator-tunable per-segment Twin delta notification thresholds."""

    __tablename__ = "twin_delta_threshold_config"

    wealth_segment: Mapped[str] = mapped_column(String(40), primary_key=True)
    positive_threshold_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    positive_threshold_absolute_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    negative_threshold_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    negative_threshold_absolute_vnd: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    expense_recompute_trigger_vnd: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), server_default=text("100000"), nullable=False
    )
    updated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)
