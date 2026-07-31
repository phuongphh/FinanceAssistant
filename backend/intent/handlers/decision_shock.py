"""Shock simulation + liquidation advice handler — Phase 4.5 / E1 (#1.3).

Answers a stress hypothetical out loud:

    "Nếu phải chi 200tr thì tài sản mình ra sao? Rút từ đâu ít hại nhất?"

Flow (fast path — one DB query, no LLM in the hot path):

    1. Flag gate at this edge. ``SHOCK_SIMULATION_ENABLED`` off → hand the
       question to the generic ``AdvisoryHandler`` so the surface behaves
       exactly as it did before Phase 4.5.
    2. Extract ``shock_amount`` from the classifier parameters. Missing it → ask
       exactly one warm clarifying question and stop.
    3. Load the portfolio snapshot (the *only* DB touch). Empty portfolio → warm
       "chưa có tài sản" copy.
    4. A shock larger than half of net worth is alarming — ask a one-line
       confirm before drawing the heavy scenario, unless the classifier already
       carries a ``shock_confirmed`` flag. This is a pure in-handler branch, not
       the pending-action machinery: no state to persist, no re-confirm loop.
    5. Run the pure ``simulate_shock`` + ``rank_options``, render the weather
       verdict + least-harmful redraw plan. Decision answers carry độ nét, so
       when the clarity meter is on we append the clarity block (same surfacing
       pattern as ``query_twin``).

Layer contract: the env reads live here at the handler edge, never in a
service. ``simulate_shock`` / ``rank_options`` and the formatter are pure; the
handler owns the single ``load_portfolio_snapshot`` read and never commits.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.clarity import render_clarity_block
from backend.bot.formatters.shock import (
    render_clarify_amount,
    render_confirm_large,
    render_empty_portfolio,
    render_shock,
)
from backend.intent.handlers.base import IntentHandler
from backend.intent.handlers.decision_flags import (
    is_clarity_meter_enabled,
    is_shock_simulation_enabled,
)
from backend.intent.intents import IntentResult
from backend.models.decision_query_log import QUERY_TYPE_SHOCK
from backend.models.user import User
from backend.services.decision import (
    clarity_service,
    cohort_service,
    decision_query_log_service,
)
from backend.services.decision.liquidation_advisor import rank_options
from backend.services.decision.shock_simulation_service import simulate_shock
from backend.twin.services.twin_projection_service import load_portfolio_snapshot

logger = logging.getLogger(__name__)

# Above this fraction of net worth, a shock is alarming enough to confirm first.
_CONFIRM_RATIO = Decimal("0.5")

# Truthy classifier values that mean "yes, show me the heavy scenario".
_CONFIRM_VALUES = frozenset({"1", "true", "yes", "on", "co", "có", "ok", "uh"})


class DecisionShockHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        # Flag gate at the edge — dark by default falls back to advisory. No log
        # here: the surface is not live, so there is no decision query to count.
        if not is_shock_simulation_enabled():
            from backend.intent.handlers.advisory import AdvisoryHandler

            return await AdvisoryHandler().handle(intent, user, db)

        answer, success, clarity_score = await self._answer(intent, user, db)
        # Phase 4.6 E4 — tag the row with the onboarding cohort so the admin
        # chart can split the new first-life segment from the legacy cohort.
        cohort = await cohort_service.resolve_user_cohort(db, user.id)
        # E5 #5.1 — one append-only row per handled query, including the
        # clarify/empty/confirm turns that never reach a verdict (success=False).
        await decision_query_log_service.log_query(
            db,
            user_id=user.id,
            query_type=QUERY_TYPE_SHOCK,
            success=success,
            clarity_score=clarity_score,
            cohort=cohort,
        )
        return answer

    async def _answer(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> tuple[str, bool, int | None]:
        """Build the reply and report ``(text, success, clarity_score)``.

        ``success`` is ``True`` only for a full shock verdict; the
        clarify/empty/confirm turns return ``False``. ``clarity_score`` is the
        độ nét surfaced with the verdict when the meter is on, else ``None``.
        """
        params = intent.parameters or {}
        shock_amount = _coerce_amount(params.get("shock_amount"))
        if shock_amount is None:
            return render_clarify_amount(), False, None

        # The single DB touch in the whole flow.
        snapshot = await load_portfolio_snapshot(db, user.id)
        if not snapshot.allocation_amounts or snapshot.base_net_worth <= 0:
            return render_empty_portfolio(), False, None

        # Confirm gate: a shock > 50% of net worth is alarming — ask once before
        # drawing the heavy scenario, unless the user already confirmed.
        if (
            shock_amount / snapshot.base_net_worth > _CONFIRM_RATIO
            and not _is_confirmed(params)
        ):
            return render_confirm_large(shock_amount), False, None

        result = simulate_shock(snapshot, shock_amount)
        plan = rank_options(snapshot.allocation_amounts, shock_amount)
        answer = render_shock(result, plan)

        # Decision answers carry độ nét — surface it exactly like query_twin.
        clarity_score: int | None = None
        if is_clarity_meter_enabled():
            clarity = await clarity_service.compute_clarity(db, user.id)
            clarity_score = clarity.score
            answer = answer + "\n\n" + render_clarity_block(clarity)
        return answer, True, clarity_score


def _coerce_amount(value) -> Decimal | None:
    """Coerce a classifier ``shock_amount`` param (int VND or numeric string)
    into a positive ``Decimal``. Returns ``None`` for anything unusable so the
    handler can ask instead of guessing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return amount if amount > 0 else None


def _is_confirmed(params: dict) -> bool:
    """Has the user already agreed to see the heavy scenario?"""
    raw = params.get("shock_confirmed")
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    return str(raw).strip().lower() in _CONFIRM_VALUES


__all__ = ["DecisionShockHandler"]
