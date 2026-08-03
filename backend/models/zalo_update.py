"""Zalo inbound event dedup + background-processing queue (Phase 5.0 #2.1).

Mirror of ``telegram_updates``. Zalo re-delivers any event we don't answer
with a 2xx, so without this table a slow handler turns one "ăn trưa 50k"
into two recorded expenses.

Dedup key is ``msg_id`` from the event body. When Zalo omits it (some
event types carry no message id), the router derives a stable surrogate —
``sha256(app_id|sender_id|timestamp|text)`` — so a retry of the *same*
delivery still collides while two genuinely identical messages sent a
second apart do not.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

# Shared with telegram_updates by convention, not by import — the two
# queues are independent and should stay free to diverge.
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


class ZaloUpdate(Base):
    __tablename__ = "zalo_updates"

    # Zalo's msg_id, or the derived surrogate described above. String
    # rather than int: Zalo's ids are opaque strings, and the surrogate is
    # a hex digest.
    msg_id: Mapped[str] = mapped_column(String(128), primary_key=True)

    # Nullable — the webhook runs before we know which user (or whether
    # there is one; unlinked senders have no row). The worker stamps it
    # once resolved, which is what makes per-user replay and GDPR-style
    # deletion possible.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    # The Zalo-side sender id. Always known, even for unlinked senders, so
    # inbound volume per sender is auditable without a user row.
    zalo_user_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=STATUS_PROCESSING, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        # Partial index — only in-flight rows matter to the orphan scan, so
        # the index stays small no matter how much history accumulates.
        Index(
            "idx_zalo_updates_processing",
            "received_at",
            postgresql_where=text("status = 'processing'"),
        ),
        Index("idx_zalo_updates_received_at", "received_at"),
    )
