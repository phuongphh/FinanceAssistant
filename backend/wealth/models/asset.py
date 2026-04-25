import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Asset(Base):
    """User-owned asset (cash, stock, real_estate, crypto, gold, other).

    JSONB ``extra`` holds per-type fields:
      - stock      → {"ticker": "VNM", "quantity": 100, "avg_price": 45000, "exchange": "HOSE"}
      - real_estate→ {"address": "...", "area_sqm": 80, "year_built": 2015}
      - crypto     → {"symbol": "BTC", "quantity": 0.5, "wallet": "Binance"}
      - gold       → {"weight_gram": 10, "type": "SJC", "purity": "9999"}

    Soft delete: when sold, ``is_active`` flips to False and ``sold_at`` /
    ``sold_value`` capture the disposition. Snapshots remain so historical
    net worth is preserved.
    """
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(50))

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    initial_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    current_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    acquired_at: Mapped[date] = mapped_column(Date, nullable=False)
    last_valued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # JSONB metadata; column name is ``extra`` to avoid SQLAlchemy's
    # reserved ``metadata`` attribute on declarative classes.
    extra: Mapped[dict | None] = mapped_column(JSONB)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sold_at: Mapped[date | None] = mapped_column(Date)
    sold_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_assets_user_active", "user_id", "is_active"),
        Index("idx_assets_type", "asset_type"),
    )

    @property
    def gain_loss(self) -> Decimal:
        """Absolute gain/loss vs initial purchase value."""
        return Decimal(self.current_value or 0) - Decimal(self.initial_value or 0)

    @property
    def gain_loss_pct(self) -> float | None:
        """Percentage gain/loss; None if initial_value is zero."""
        initial = Decimal(self.initial_value or 0)
        if initial == 0:
            return None
        return float(self.gain_loss / initial * 100)
