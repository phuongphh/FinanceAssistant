"""Zalo 48h reply window + free-message quota (Phase 5.0 #3.1).

Zalo only lets an OA send consulting (CS) messages within 48 hours of the
user's last inbound message, capped at 8 messages per window. Both limits
are enforced on Zalo's side; this table is our local accounting so we stop
*before* burning a rejection.

One row per ``zalo_user_id``. The counter is reset — not incremented —
whenever a new inbound message opens a fresh window.

All timestamps are UTC. ``window_expires_at`` is stored, never recomputed
from a local-time boundary, so the Asia/Ho_Chi_Minh offset can't shift it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

# Platform constants — see docs/conventions/zalo-operations.md §Message sending.
WINDOW_HOURS = 48
FREE_MESSAGE_QUOTA = 8


class ZaloMessageWindow(Base):
    __tablename__ = "zalo_message_window"

    zalo_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Nullable for the same reason as zalo_updates.user_id: a sender can
    # message the OA before (or without ever) linking an account.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    last_inbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # last_inbound_at + 48h, materialised so the quota UPDATE can compare
    # against it in one predicate without arithmetic in the WHERE clause.
    window_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Sends reserved in the CURRENT window. Reset by record_inbound — down
    # to the reservations still in flight, not to 0, because a send Zalo
    # is still processing will be charged to whichever window it lands in.
    free_msg_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Of those, how many have not yet come back from the OA. Bumped by
    # reserve_send, cleared by settle_send (delivered or refused) or
    # release_send (refunded). Always <= free_msg_count.
    inflight_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_zalo_message_window_expires", "window_expires_at"),
    )
