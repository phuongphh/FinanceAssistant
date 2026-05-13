from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


POSITIONING_EXPENSE_TRACKER = "expense_tracker"
POSITIONING_PERSONAL_CFO = "personal_cfo"
POSITIONING_FUTURE_TOOL = "future_tool"
POSITIONING_UNCLEAR = "unclear"

VALID_POSITIONING_RESPONSES = frozenset(
    {
        POSITIONING_EXPENSE_TRACKER,
        POSITIONING_PERSONAL_CFO,
        POSITIONING_FUTURE_TOOL,
        POSITIONING_UNCLEAR,
    }
)
ALIGNED_POSITIONING_RESPONSES = frozenset(
    {POSITIONING_PERSONAL_CFO, POSITIONING_FUTURE_TOOL}
)
MISALIGNED_POSITIONING_RESPONSES = frozenset(
    {POSITIONING_EXPENSE_TRACKER, POSITIONING_UNCLEAR}
)


class PositioningSurveyResponse(Base):
    """One-shot Day 7 positioning micro-survey response.

    Stored separately from generic feedback because this is a product
    health KPI: every user can answer at most once, and the digest needs
    fast grouped counts without scanning free-form feedback rows.
    """

    __tablename__ = "positioning_survey_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    response: Mapped[str] = mapped_column(String(32), nullable=False)
    source_prompt_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_positioning_survey_user_id"),
        Index("idx_positioning_survey_response", "response"),
        Index("idx_positioning_survey_created_at", "created_at"),
    )
