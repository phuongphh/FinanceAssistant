"""Short-term conversation context — rolling buffer of recent turns.

Each row is one message (user or assistant). The agent layer reads the
last N rows (TTL-filtered) before each LLM call so follow-up questions
can resolve against prior turns. Append-only — never edit a row.

Why a separate table instead of reusing ``events``:
- Two roles (user / assistant) interleave; events is single-actor.
- We want fast "last N rows for user X" reads, which the (user_id,
  created_at DESC) index serves directly.
- Content is truncated; events.properties is a JSON blob — different
  storage shape and access pattern.

PII note: ``content`` contains raw user input and a truncated summary
of bot output. Same sensitivity as the agent_audit_logs.query_text
field; revisit before opening up to multi-tenant.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


class ConversationContext(Base):
    __tablename__ = "conversation_context"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index(
            "idx_conv_ctx_user_time",
            "user_id",
            "created_at",
            postgresql_using="btree",
        ),
    )
