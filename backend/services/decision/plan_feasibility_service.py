"""Plan-to-goal feasibility Q&A — Phase 4.5 / E2 (#2.1).

The user asks a *hypothetical* out loud:

    "Mình đang có 200tr, muốn có 1 tỷ sau 5 năm — có khả thi không?"

This is different from ``goal_projection`` (which reads a *saved* goal from
the DB). Here nothing is persisted: the numbers arrive in the question and
we answer on the spot. So ``assess`` is **pure** — the only DB touch in the
whole flow is the caller's single ``get_avg_monthly_savings`` query, which
it passes in as ``avg_monthly_savings``. That keeps the layer contract
clean (no env, no writes) and the response fast (one query, no LLM).

We deliberately **reuse** the existing feasibility engine rather than
re-derive the bands: a hypothetical is just a goal we never saved, so we
wrap the inputs in a throw-away goal-shaped object and hand it to
``project_goal_with_savings``. One source of truth for what "khả thi"
means across saved goals and hypotheticals — including the month count,
which we read back from the projection instead of recomputing.

When the target is out of reach at the user's current saving rate, we don't
stop at "no". We compute the **honest reachable target** — the largest
amount they *could* hit in that horizon at their current rate — so Bé Tiền
can pivot from a flat rejection to "đây là mức mình với tới được nha".
Because required savings is linear in the target, that boundary is
closed-form (target ≤ start + savings × months); no search needed. We round
it *down* to a clean milestone so the promise stays conservative.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from backend.schemas.goal import FeasibilityBand, GoalProjection
from backend.services.goal_projection import project_goal_with_savings

# Bands that mean "you can hit the actual target" — no honest-alternative
# pivot needed. Everything else gets a ``reachable_target``.
_ACHIEVABLE_BANDS = frozenset({FeasibilityBand.EASY, FeasibilityBand.FEASIBLE})

_DAYS_PER_YEAR = Decimal("365.25")


@dataclass(frozen=True)
class _HypotheticalGoal:
    """Goal-shaped duck for ``project_goal_with_savings``.

    That engine reads only ``id``, ``target_amount``, ``current_amount`` and
    ``target_date``. ``goal_id`` on the projection is a required UUID, so we
    mint a throw-away one — it never touches the DB.
    """

    id: uuid.UUID
    target_amount: Decimal
    current_amount: Decimal
    target_date: date | None


@dataclass(frozen=True)
class PlanFeasibility:
    """Answer to a hypothetical "is this reachable?" question.

    ``reachable_target`` is ``None`` when the user can already hit their
    stated target (EASY/FEASIBLE) — otherwise it's the honest, rounded-down
    amount they *could* reach at their current rate, so the copy can pivot
    instead of just saying no.
    """

    band: FeasibilityBand
    months: int
    remaining: Decimal
    actual_monthly_savings: Decimal
    required_monthly_savings: Decimal | None
    reachable_target: Decimal | None
    already_reached: bool
    projection: GoalProjection
    notes: list[str] = field(default_factory=list)


def assess(
    start: Decimal,
    target: Decimal,
    horizon_years: Decimal,
    avg_monthly_savings: Decimal,
    *,
    today: date | None = None,
) -> PlanFeasibility:
    """Assess whether ``start`` can grow to ``target`` within
    ``horizon_years`` at ``avg_monthly_savings`` per month.

    Pure: no DB, no clock beyond the injectable ``today``. All money is
    ``Decimal``. Reuses ``project_goal_with_savings`` for the band so the
    definition of "khả thi" matches saved-goal feasibility exactly.
    """
    today = today or date.today()
    start = Decimal(start)
    target = Decimal(target)
    savings = Decimal(avg_monthly_savings)
    if savings < 0:
        savings = Decimal(0)

    target_date = _target_date_from_years(today, horizon_years)

    goal = _HypotheticalGoal(
        id=uuid.uuid4(),
        target_amount=target,
        current_amount=start,
        target_date=target_date,
    )
    projection = project_goal_with_savings(goal, savings, today=today)

    # The projection owns the month count (its ``_months_between`` is the
    # authority) — read it back so ``months`` and the band never disagree.
    months = projection.months_remaining or _months_from_years(horizon_years)

    remaining = target - start
    if remaining <= 0:
        # Already there (or ahead). The engine returns a cheerful note and
        # no feasibility band — surface that as an explicit "done" state.
        return PlanFeasibility(
            band=FeasibilityBand.EASY,
            months=months,
            remaining=Decimal(0),
            actual_monthly_savings=savings,
            required_monthly_savings=None,
            reachable_target=None,
            already_reached=True,
            projection=projection,
            notes=list(projection.notes),
        )

    band = projection.feasibility or FeasibilityBand.UNKNOWN
    reachable = None
    if band not in _ACHIEVABLE_BANDS:
        reachable = _reachable_target(start, savings, months)

    return PlanFeasibility(
        band=band,
        months=months,
        remaining=remaining,
        actual_monthly_savings=savings,
        required_monthly_savings=projection.required_monthly_savings,
        reachable_target=reachable,
        already_reached=False,
        projection=projection,
        notes=list(projection.notes),
    )


# ---------------------------------------------------------------------
# Honest reachable-target math
# ---------------------------------------------------------------------


def _reachable_target(start: Decimal, savings: Decimal, months: int) -> Decimal:
    """Largest target reachable at ``savings``/month over ``months``.

    A target is FEASIBLE when required ≤ actual, i.e.
    ``(target − start) / months ≤ savings`` → ``target ≤ start + savings ×
    months``. Closed-form, so no binary search. We round *down* to a clean
    milestone so we never over-promise: the rounded target needs strictly
    less than the user's current rate, landing safely inside FEASIBLE.
    """
    if savings <= 0 or months <= 0:
        return _round_down_milestone(start)
    ceiling = start + savings * Decimal(months)
    return _round_down_milestone(ceiling)


def _round_down_milestone(amount: Decimal) -> Decimal:
    """Floor ``amount`` to a magnitude-appropriate 'nice' step.

    Keeps the honest-alternative number readable ("khoảng 850tr" not
    "847.312.905đ") and conservative (always ≤ the real ceiling).
    """
    if amount <= 0:
        return Decimal(0)
    if amount >= Decimal("1_000_000_000"):
        step = Decimal("50_000_000")
    elif amount >= Decimal("100_000_000"):
        step = Decimal("10_000_000")
    elif amount >= Decimal("10_000_000"):
        step = Decimal("1_000_000")
    else:
        step = Decimal("500_000")
    return (amount // step) * step


# ---------------------------------------------------------------------
# Horizon helpers
# ---------------------------------------------------------------------


def _target_date_from_years(today: date, horizon_years: Decimal) -> date:
    """Convert a fuzzy 'X năm' horizon into a concrete target date. The
    projection derives the authoritative month count from this date, so we
    only need it close enough for the user's mental model."""
    days = int(round(float(Decimal(horizon_years) * _DAYS_PER_YEAR)))
    return today + timedelta(days=max(days, 1))


def _months_from_years(horizon_years: Decimal) -> int:
    """Fallback month count for the already-reached branch, where the
    projection short-circuits before computing ``months_remaining``."""
    months = int(Decimal(horizon_years) * Decimal(12))
    return max(months, 1)


__all__ = ["PlanFeasibility", "assess"]
