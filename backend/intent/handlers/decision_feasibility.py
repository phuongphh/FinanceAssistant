"""Plan-to-goal feasibility Q&A handler — Phase 4.5 / E2 (#2.2).

Answers a *hypothetical* out loud:

    "Mình muốn có 1 tỷ sau 5 năm — có khả thi không?"

Flow (fast path — one DB query, no LLM in the hot path):

    1. Flag gate at this edge. ``PLAN_FEASIBILITY_QA_ENABLED`` off → hand the
       question to the generic ``AdvisoryHandler`` so the surface behaves
       exactly as it did before Phase 4.5.
    2. Extract ``target`` + ``horizon_years`` (and optional ``start``) from the
       classifier parameters. Missing an essential one → ask exactly one warm
       clarifying question and stop.
    3. Read the user's average monthly saving rate (the *only* DB touch), run
       the pure ``plan_feasibility_service.assess``, render the verdict.

Layer contract: the env read lives here at the handler edge, never in a
service. ``assess`` and the formatter are pure; the handler owns the single
``get_avg_monthly_savings`` read and never commits.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.feasibility import render_clarify, render_feasibility
from backend.bot.formatters.tone import resolve_tone
from backend.intent.handlers.base import IntentHandler
from backend.intent.handlers.decision_flags import (
    is_plan_feasibility_qa_enabled,
    is_tone_dial_enabled,
)
from backend.intent.intents import IntentResult
from backend.models.decision_query_log import QUERY_TYPE_FEASIBILITY
from backend.models.user import User
from backend.services.decision import decision_query_log_service, plan_feasibility_service
from backend.services.goal_projection import get_avg_monthly_savings
from backend.services.onboarding.onboarding_service import salutation_of

logger = logging.getLogger(__name__)

# Clamp a fuzzy horizon so a fat-fingered "500 năm" can't spin the projection.
_MAX_HORIZON_YEARS = Decimal(60)


class DecisionFeasibilityHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        # Flag gate at the edge — dark by default falls back to advisory. No log
        # here: the surface is not live, so there is no decision query to count.
        if not is_plan_feasibility_qa_enabled():
            from backend.intent.handlers.advisory import AdvisoryHandler

            return await AdvisoryHandler().handle(intent, user, db)

        answer, success = await self._answer(intent, user, db)
        # E5 #5.1 — one append-only row per handled query, including the
        # clarify turns that never reach a verdict (success=False).
        await decision_query_log_service.log_query(
            db,
            user_id=user.id,
            query_type=QUERY_TYPE_FEASIBILITY,
            success=success,
        )
        return answer

    async def _answer(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> tuple[str, bool]:
        """Build the reply and report ``(text, success)``.

        ``success`` is ``True`` only for a full feasibility verdict; the two
        clarify turns return ``False``.
        """
        params = intent.parameters or {}
        target = _coerce_amount(params.get("target_amount"))
        horizon = _coerce_years(params.get("horizon_years"))
        # Start is optional — "muốn có 1 tỷ sau 5 năm" starts fresh (0).
        start = _coerce_amount(params.get("start_amount")) or Decimal(0)

        if target is None:
            return render_clarify("target"), False
        if horizon is None:
            return render_clarify("horizon", target=target), False

        # The single DB touch in the whole flow.
        avg_savings = await get_avg_monthly_savings(db, user.id)
        result = plan_feasibility_service.assess(start, target, horizon, avg_savings)
        # Tone dial read at the edge (layer contract); dark → tone=None → the
        # formatter keeps its legacy copy.
        tone = resolve_tone(user.tone_preference) if is_tone_dial_enabled() else None
        return (
            render_feasibility(
                result,
                target=target,
                horizon_years=horizon,
                tone=tone,
                salutation=salutation_of(user),
            ),
            True,
        )


def _coerce_amount(value) -> Decimal | None:
    """Coerce a classifier ``amount`` param (int VND, or numeric string) into a
    positive ``Decimal``. Returns ``None`` for anything unusable so the handler
    can ask instead of guessing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return amount if amount > 0 else None


def _coerce_years(value) -> Decimal | None:
    """Coerce a horizon param into a positive ``Decimal`` number of years,
    clamped to a sane ceiling. ``None`` when unusable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        years = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    if years <= 0:
        return None
    return min(years, _MAX_HORIZON_YEARS)


__all__ = ["DecisionFeasibilityHandler"]
