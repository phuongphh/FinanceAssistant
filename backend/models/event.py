from __future__ import annotations

"""Analytics event model.

Append-only — every user action that matters for product metrics
(button taps, Mini App loads, transaction sources, etc.) gets a row
here. Strictly no PII: no merchant names, no amounts, no message text.
Schema details + rationale in `docs/tone_guide.md` → Metrics section.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable — some events fire before a user is resolved (e.g. webhook
    # received but user not registered yet).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    properties: Mapped[dict | None] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )

    __table_args__ = (
        Index("idx_events_user_type", "user_id", "event_type"),
        Index("idx_events_type_timestamp", "event_type", "timestamp"),
    )
