from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class TwinProjection(Base):
    """Persisted Financial Twin probability cone.

    Rows are immutable snapshots of what the engine predicted at compute time.
    Keeping the frozen inputs and outputs enables future "prediction vs actual"
    audits without recomputing history with a newer engine version.
    """

    __tablename__ = "twin_projections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    horizon_years: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario: Mapped[str] = mapped_column(String(20), nullable=False)

    base_net_worth: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    monthly_savings: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    allocation_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    cone_data: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    sim_paths: Mapped[int] = mapped_column(
        Integer, server_default=text("1000"), nullable=False
    )
    seed: Mapped[int | None] = mapped_column(BigInteger)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    actual_net_worth: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)

    __table_args__ = (
        Index("idx_twin_proj_user_latest", "user_id", "computed_at"),
        Index("idx_twin_proj_user_scenario", "user_id", "scenario", "computed_at"),
    )
