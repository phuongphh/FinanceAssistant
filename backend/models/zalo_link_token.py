"""Phase 4B Epic 4 — short-lived Zalo linking tokens.

A Telegram user runs ``/link_zalo`` and gets a 6-char code ``BT-XXXXXX``.
They paste that code into the Zalo OA chat. The Zalo webhook looks the
code up here and binds the Zalo user_id to the Telegram-resolved user.

Tokens are single-use (``used_at`` set on redemption) and expire after
10 minutes so an unredeemed token can't sit around as a long-lived
binding credential. We keep the row instead of deleting it so analytics
can tell apart "expired" (timeout) from "used elsewhere" (already paired).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ZaloLinkToken(Base):
    __tablename__ = "zalo_link_tokens"

    # Human-typeable token (e.g. "BT-A7K3P2"). Primary key — Zalo
    # webhook matches verbatim so we never index a derived column.
    token: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Set when the token is redeemed via the Zalo webhook. NULL = unused.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
