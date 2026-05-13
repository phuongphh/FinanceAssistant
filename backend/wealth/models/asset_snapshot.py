import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class AssetSnapshot(Base):
    """Daily historical value for an asset.

    Created (a) when user updates an asset's current_value, (b) by the
    23:59 daily snapshot job (source=``auto_daily``), or (c) by market
    poller jobs in Phase 3B (source=``market_api``).

    Unique on ``(asset_id, snapshot_date)`` keeps the daily job
    idempotent — re-runs use INSERT ... ON CONFLICT DO NOTHING.
    """
    __tablename__ = "asset_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("asset_id", "snapshot_date", name="uq_asset_snapshot_date"),
        Index("idx_snapshots_user_date", "user_id", "snapshot_date"),
    )
