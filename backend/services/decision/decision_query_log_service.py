"""Flush-only writer for the Decision-Engine query log — Phase 4.5 / E5 (#5.1).

Every handled decision query (shock simulation, plan feasibility) drops one
append-only row here, whether or not it reached a verdict: a clarify / empty /
confirm turn is logged with ``success=False`` so the funnel shows where users
stall. The Phase 4.6 admin dashboard reads this; Phase 4.5 only writes.

Layer contract: this is a service, so it **flushes, never commits** — the
caller (worker/router) owns the transaction boundary. It reads no env and
touches no transport.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.decision_query_log import DecisionQueryLog

logger = logging.getLogger(__name__)


async def log_query(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_type: str,
    success: bool,
    clarity_score: Decimal | int | None = None,
    cohort: str | None = None,
) -> DecisionQueryLog:
    """Append one decision-query row and flush.

    ``clarity_score`` is the độ nét at answer time (0..100) when the clarity
    meter is on, else ``None``. An ``int`` score is accepted and coerced to
    ``Decimal`` so callers can pass ``ClarityResult.score`` straight through.

    ``cohort`` is the onboarding cohort tag (Phase 4.6 / E4) — "reset" /
    "legacy" / ``None`` — already classified by the caller so this service
    stays a pure writer. ``None`` leaves the row unattributed.
    """
    score = Decimal(clarity_score) if clarity_score is not None else None
    row = DecisionQueryLog(
        user_id=user_id,
        query_type=query_type,
        success=success,
        clarity_score=score,
        cohort=cohort,
    )
    db.add(row)
    await db.flush()
    return row


__all__ = ["log_query"]
