from __future__ import annotations

"""User milestone model — Memory Moments feature (Phase 2).

Each row records a single recognised moment in the user's journey:
the 7-day anniversary, the first time they saved 10% of income, the
100-day streak, etc. The milestone service writes rows when it detects
a new achievement; the daily scheduler then sends a celebration
message and stamps `celebrated_at`.

`(user_id, milestone_type)` is unique so retries and re-runs are safe.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class UserMilestone(Base):
    __tablename__ = "user_milestones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    milestone_type: Mapped[str] = mapped_column(String(50), nullable=False)
    achieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    celebrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # `metadata` is reserved by SQLAlchemy's Declarative base — stored under
    # `extra` in the DB but exposed to callers as a plain dict.
    extra: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("user_id", "milestone_type", name="uq_user_milestone_type"),
        Index("idx_milestones_user_type", "user_id", "milestone_type"),
        Index("idx_milestones_celebrated_at", "celebrated_at"),
    )


class MilestoneType:
    """Canonical milestone type codes.

    Used as `UserMilestone.milestone_type` values and as keys into
    `content/milestone_messages.yaml`. Add new codes here before wiring
    detection logic so the source of truth stays in one place.
    """
    # Time-based
    FIRST_TRANSACTION = "first_transaction"
    DAYS_7 = "days_7"
    DAYS_30 = "days_30"
    DAYS_100 = "days_100"
    DAYS_365 = "days_365"

    # Behavior-based
    FIRST_BUDGET_SET = "first_budget_set"
    FIRST_CATEGORY_CHANGE = "first_category_change"
    FIRST_VOICE_INPUT = "first_voice_input"
    FIRST_PHOTO_INPUT = "first_photo_input"

    # Financial
    SAVE_10_PERCENT_MONTHLY = "save_10_percent_monthly"
    SAVE_20_PERCENT_MONTHLY = "save_20_percent_monthly"
    SAVINGS_1M = "savings_1m"
    SAVINGS_5M = "savings_5m"
    SAVINGS_10M = "savings_10m"
    SAVINGS_50M = "savings_50m"

    # Streak
    STREAK_7 = "streak_7"
    STREAK_30 = "streak_30"
    STREAK_100 = "streak_100"

    # Wealth-level transitions (#155). No UP_STARTER (users start there)
    # and no DOWN_HNW (no higher band to descend from).
    WEALTH_LEVEL_UP_YOUNG_PROF = "wealth_level_up_young_prof"
    WEALTH_LEVEL_UP_MASS_AFFLUENT = "wealth_level_up_mass_affluent"
    WEALTH_LEVEL_UP_HNW = "wealth_level_up_hnw"
    WEALTH_LEVEL_DOWN_STARTER = "wealth_level_down_starter"
    WEALTH_LEVEL_DOWN_YOUNG_PROF = "wealth_level_down_young_prof"
    WEALTH_LEVEL_DOWN_MASS_AFFLUENT = "wealth_level_down_mass_affluent"

    @classmethod
    def all(cls) -> list[str]:
        return [
            v for k, v in cls.__dict__.items()
            if not k.startswith("_") and isinstance(v, str)
        ]
