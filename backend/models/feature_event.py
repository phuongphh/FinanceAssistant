from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class FeatureEvent(Base):
    """Append-only feature interaction stream for admin observability.

    This table is intentionally separate from the generic ``events`` stream:
    feature-click charts need a stable, low-cardinality ``feature_key`` while
    existing product events can remain granular and handler-specific.
    """

    __tablename__ = "feature_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    feature_key: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_feature_events_user", "user_id"),
        Index("idx_feature_events_feature", "feature_key", "created_at"),
        Index("idx_feature_events_created", "created_at"),
    )
