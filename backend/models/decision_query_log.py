from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

# Which Decision-Engine surface produced the log row. Kept as short stable
# codes (not free text) so the Phase 4.6 admin chart can group without a
# lookup table.
QUERY_TYPE_SHOCK = "shock"
QUERY_TYPE_FEASIBILITY = "feasibility"
# Phase 4.7 / E2 — user-initiated scam check ("kèo này có nên không?"). Only
# this *user-initiated* Guardian surface logs here. Proactive drift warnings
# (Phase 4.7 / E1) deliberately do NOT: they stamp the empathy ``empathy_fired``
# event stream instead, because ``/charts/decision-adoption`` (see
# ``backend/api/admin/analytics.py``) aggregates every row in this table with no
# ``query_type`` filter, so logging a proactive nudge here would inflate the
# G1/G2 adoption + active-user metrics. Fits ``String(32)`` — no migration.
QUERY_TYPE_SCAM_CHECK = "scam_check"

VALID_QUERY_TYPES = frozenset(
    {QUERY_TYPE_SHOCK, QUERY_TYPE_FEASIBILITY, QUERY_TYPE_SCAM_CHECK}
)


class DecisionQueryLog(Base):
    """Append-only log of every Decision-Engine question a user asks.

    One row per handled decision query (shock simulation, plan feasibility),
    logged whether or not the user got a full verdict — a clarify/empty/confirm
    turn is a ``success=False`` row so the funnel shows where users stall.

    This table is **write-only in Phase 4.5**: it feeds the G1/G2 gates and the
    Phase 4.6 admin dashboard chart. It is never mutated or soft-deleted — a log
    is a fact, so there is no ``deleted_at``/``is_active``.
    """

    __tablename__ = "decision_query_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    query_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Độ nét at answer time, when the clarity meter is on — 0..100 stored as
    # NUMERIC(5,2) to leave room for a future fractional score. NULL when the
    # meter was off or the turn never reached a verdict.
    clarity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Onboarding cohort at answer time (Phase 4.6 / E4), derived from the chosen
    # goal via ``onboarding_session.cohort_for_goal`` — "reset" (first-life
    # segment) / "legacy" (asset-management). NULL when the goal is unknown or
    # no session exists, so the admin chart can split the new segment out.
    cohort: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_decision_query_log_user_id", "user_id"),
        Index("idx_decision_query_log_query_type", "query_type"),
        Index("idx_decision_query_log_created_at", "created_at"),
        Index("idx_decision_query_log_cohort", "cohort"),
    )


__all__ = [
    "DecisionQueryLog",
    "QUERY_TYPE_SHOCK",
    "QUERY_TYPE_FEASIBILITY",
    "QUERY_TYPE_SCAM_CHECK",
    "VALID_QUERY_TYPES",
]
