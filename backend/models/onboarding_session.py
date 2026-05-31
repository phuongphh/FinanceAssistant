"""Onboarding state machine (Phase 4.1, Story A.1).

The legacy 5-step onboarding tracked progress on the ``users`` row
itself; the v2 goal-based flow needs richer state (goal pick, inferred
wealth segment, in-onboarding emoji feedback, resume nudge bookkeeping,
TTFT timing) so it gets its own table.

States:

- ``goal_question``: user has /start-ed, awaiting goal pick.
- ``first_asset``: goal chosen, awaiting asset amount or "use demo".
- ``twin_shown``: first Twin computed + sent, awaiting feedback emoji
  or natural drop-off.
- ``completed``: terminal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


STEP_GOAL_QUESTION = "goal_question"
STEP_TRUST_PRIVACY = "trust_privacy"
STEP_FIRST_ASSET = "first_asset"
STEP_TWIN_SHOWN = "twin_shown"
STEP_COMPLETED = "completed"

# Phase 4.4 Epic 0 — salutation pick (how Bé Tiền addresses the user).
# Stored on users.salutation; "bạn" is the gender-neutral fallback used
# whenever the column is NULL.
SALUTATION_ANH = "anh"
SALUTATION_CHI = "chị"
SALUTATION_BAN = "bạn"
ALL_SALUTATIONS = (SALUTATION_ANH, SALUTATION_CHI, SALUTATION_BAN)
DEFAULT_SALUTATION = SALUTATION_BAN

# Goal codes — used by content/onboarding/welcome_v2.yaml + analytics.
GOAL_UNDERSTAND_WEALTH = "understand_wealth"
GOAL_PLAN_GOAL = "plan_goal"
GOAL_TRACK_SPENDING = "track_spending"
ALL_GOALS = (GOAL_UNDERSTAND_WEALTH, GOAL_PLAN_GOAL, GOAL_TRACK_SPENDING)

# Wealth segments — inferred from first asset value (not self-reported).
SEGMENT_STARTER = "starter"
SEGMENT_YOUNG_PRO = "young_pro"
SEGMENT_MASS_AFFLUENT = "mass_affluent"
SEGMENT_HNW = "hnw"

# In-onboarding emoji signal options (after first Twin).
SIGNAL_LOVE = "love"
SIGNAL_CONFUSED = "confused"
SIGNAL_DISLIKE = "dislike"


class OnboardingSession(Base):
    __tablename__ = "onboarding_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    current_step: Mapped[str] = mapped_column(
        String(32), default=STEP_GOAL_QUESTION, nullable=False
    )
    goal_choice: Mapped[str | None] = mapped_column(String(32))
    inferred_wealth_segment: Mapped[str | None] = mapped_column(String(32))
    first_asset_value_vnd: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    demo_mode_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_twin_shown_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Phase 4.2 Epic 1 — trust moment between goal and asset input.
    trust_shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trust_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trust_question_raised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Phase 4.2 Epic 2 fields are migrated with the same trust-state task
    # so later activation stories do not need another hot table ALTER.
    next_best_action_taken: Mapped[str | None] = mapped_column(String(50))
    next_best_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nudge_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarding_feedback_signal: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
