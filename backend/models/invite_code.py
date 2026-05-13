"""Invite codes for soft-launch acquisition (Phase 4.1, Story C.1).

Each row is one ``t.me/BeTienBot?start=invite_<token>`` link. Tokens
that ``grants_founding_status=TRUE`` mark the redeemer as a founding
member (sequence 1..50). Single-use: once redeemed the row is locked
to that user.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_name: Mapped[str | None] = mapped_column(String(64))
    grants_founding_status: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    redeemed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
