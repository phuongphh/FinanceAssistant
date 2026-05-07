from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


FEEDBACK_STATUS_NEW = "new"
FEEDBACK_STATUS_REVIEWING = "reviewing"
FEEDBACK_STATUS_ACTIONED = "actioned"
FEEDBACK_STATUS_DISMISSED = "dismissed"

PROMPT_STATUS_SENT = "sent"
PROMPT_STATUS_SKIPPED = "skipped"
PROMPT_STATUS_RESPONDED = "responded"


class Feedback(Base):
    """Free-form user feedback with deferred backend classification."""

    __tablename__ = "feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    category: Mapped[str | None] = mapped_column(String(50), index=True)
    sentiment: Mapped[str | None] = mapped_column(String(20), index=True)
    priority: Mapped[str | None] = mapped_column(String(20), index=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    classifier_version: Mapped[str | None] = mapped_column(String(50))
    classification_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classification_error: Mapped[str | None] = mapped_column(Text)

    trigger: Mapped[str] = mapped_column(String(80), default="passive_command", nullable=False, index=True)
    context: Mapped[dict | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(20), default=FEEDBACK_STATUS_NEW, nullable=False, index=True)
    admin_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_feedbacks_user_created_at", "user_id", "created_at"),
        Index(
            "idx_feedbacks_unclassified",
            "created_at",
            postgresql_where=text("category IS NULL"),
        ),
    )


class PromptSentLog(Base):
    """Audit table for active feedback prompts and user responses."""

    __tablename__ = "prompts_sent_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    prompt_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=PROMPT_STATUS_SENT, nullable=False, index=True)
    context: Mapped[dict | None] = mapped_column(JSONB)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_prompts_user_prompt_sent", "user_id", "prompt_id", "sent_at"),
        Index("idx_prompts_user_sent", "user_id", "sent_at"),
    )
