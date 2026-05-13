from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    asset_code: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_name: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[float | None] = mapped_column(Numeric(15, 4))
    change_1d_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    change_1w_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    change_1m_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("snapshot_date", "asset_code", name="uq_snapshot_date_asset"),
        Index("idx_market_date", "snapshot_date"),
        Index("idx_market_asset", "asset_code", "snapshot_date"),
    )
