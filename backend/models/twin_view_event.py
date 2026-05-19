from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class TwinViewEvent(Base):
    """Append-only Twin storytelling event stream for funnel analytics."""

    __tablename__ = "twin_view_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    screen_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    flow_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (
        Index("idx_twin_view_events_user_created", "user_id", "created_at"),
        Index("idx_twin_view_events_type_created", "event_type", "created_at"),
        Index("idx_twin_view_events_screen_created", "screen_id", "created_at"),
    )
