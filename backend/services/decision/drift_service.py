"""Spending-drift assessment + Twin consequence — Phase 4.7 / E1 (#1.1).

Decision Moment #3: the user's spending has drifted above their own recent
baseline. A bare "you overspent" is noise; what makes it *land* is the concrete
Twin consequence — "giữ nhịp này, mốc mua nhà lùi 14 tháng". So this module
does two things and nothing else:

1. **Baseline + drift** — baseline is the median non-transfer spend across the
   three prior 30-day windows; drift is the current 30-day window measured
   against it. We fire only when the overshoot clears BOTH a percentage
   threshold (relative) AND an absolute VND floor (so a user whose baseline is
   tiny doesn't get warned over a rounding-error overshoot).
2. **Twin consequence** — if the user keeps this drifted pace, their monthly
   saving rate shrinks by the drift amount, so their nearest goal completes
   later. We reuse the same saving-rate arithmetic the goal projection uses
   (remaining ÷ monthly savings = months) and report the *delay* in months.

``assess`` is **pure**: no DB, no env, no clock, no writes, all ``Decimal``.
The DB-facing ``compute_drift`` gathers the windows + goal + saving rate and
hands them to ``assess`` — mirroring ``goal_projection`` (async reader that
never commits) and ``plan_feasibility`` (pure ``assess`` under a thin gatherer).
The empathy trigger (#1.2) calls ``compute_drift``.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.user import User
from backend.services.goal_projection import get_avg_monthly_savings

# Categories that are internal movements of the user's own money, not
# consumption — excluded from the baseline and the current window so a big
# transfer to savings never reads as a spending blow-out. Mirrors the empathy
# engine's ``_INTERNAL_CATEGORIES``.
_INTERNAL_CATEGORIES = frozenset({"transfer", "saving", "savings", "investment"})

# A drift fires only when the current window exceeds baseline by BOTH:
#   - ``DEFAULT_DRIFT_PCT`` (relative) — a real change of pace, not noise, and
#   - ``DEFAULT_DRIFT_ABS_FLOOR`` (absolute VND) — worth a nudge in real money.
# Owner-signed defaults (phase-4.7-detailed.md, Owner-Decision #2). Both are
# parameters so tests and a future per-user tune can override them.
DEFAULT_DRIFT_PCT = Decimal("0.20")
DEFAULT_DRIFT_ABS_FLOOR = Decimal("1000000")  # 1tr

# Number of prior 30-day windows the baseline median is taken over. Below this
# the baseline is not trustworthy, so we do not fire ("<3 tháng data").
MIN_HISTORY_WINDOWS = 3

_WINDOW_DAYS = 30


@dataclass(frozen=True)
class DriftAssessment:
    """Result of a drift check.

    ``is_drifting`` is the gate the trigger reads. ``goal_delay_months`` is the
    concrete Twin consequence when it can be computed (drifting, a goal with
    remaining > 0, a positive baseline saving rate, and a slip of ≥ 1 month) —
    otherwise ``None`` and the copy falls back to a no-delta variant.
    ``pace_unsustainable`` marks the case where the drift would erase the whole
    saving rate (new rate ≤ 0), so the goal effectively stalls rather than
    merely slipping.
    """

    baseline: Decimal
    current_spend: Decimal
    drift_amount: Decimal  # current - baseline (VND / 30-day window)
    drift_pct: Decimal  # drift_amount / baseline
    is_drifting: bool
    goal_label: str | None
    goal_delay_months: int | None
    pace_unsustainable: bool


def assess(
    baseline_history: Sequence[Decimal],
    current_spend: Decimal,
    *,
    goal_remaining: Decimal | None,
    avg_monthly_savings: Decimal,
    goal_label: str | None = None,
    threshold_pct: Decimal = DEFAULT_DRIFT_PCT,
    absolute_floor: Decimal = DEFAULT_DRIFT_ABS_FLOOR,
) -> DriftAssessment | None:
    """Assess whether ``current_spend`` has drifted above the baseline.

    ``baseline_history`` is the non-transfer spend of each prior 30-day window
    (order irrelevant — we take the median). Returns ``None`` when there is not
    enough history (fewer than ``MIN_HISTORY_WINDOWS`` windows) or the baseline
    is non-positive — in both cases we have no trustworthy reference to drift
    against. Otherwise returns a ``DriftAssessment`` whose ``is_drifting`` tells
    the caller whether to nudge.

    Pure: no DB, no env, no clock. All money is ``Decimal``.
    """
    if len(baseline_history) < MIN_HISTORY_WINDOWS:
        return None

    baseline = _median(baseline_history)
    if baseline <= 0:
        return None

    current = Decimal(current_spend)
    drift_amount = current - baseline
    drift_pct = drift_amount / baseline

    is_drifting = drift_amount >= absolute_floor and drift_pct >= threshold_pct

    goal_delay_months: int | None = None
    pace_unsustainable = False
    if is_drifting and goal_remaining is not None and goal_remaining > 0:
        savings = Decimal(avg_monthly_savings)
        if savings > 0:
            drifted_savings = savings - drift_amount
            if drifted_savings <= 0:
                # The drift would swallow the entire saving rate — the goal
                # doesn't just slip, it stalls. Surface that distinctly.
                pace_unsustainable = True
            else:
                baseline_months = _months_to_reach(goal_remaining, savings)
                drifted_months = _months_to_reach(goal_remaining, drifted_savings)
                delay = drifted_months - baseline_months
                if delay >= 1:
                    goal_delay_months = delay

    return DriftAssessment(
        baseline=baseline,
        current_spend=current,
        drift_amount=drift_amount,
        drift_pct=drift_pct,
        is_drifting=is_drifting,
        goal_label=goal_label,
        goal_delay_months=goal_delay_months,
        pace_unsustainable=pace_unsustainable,
    )


async def compute_drift(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
    threshold_pct: Decimal = DEFAULT_DRIFT_PCT,
    absolute_floor: Decimal = DEFAULT_DRIFT_ABS_FLOOR,
) -> DriftAssessment | None:
    """Gather the windows, nearest goal, and saving rate, then ``assess``.

    Read-only: this reads several tables but never writes or commits (layer
    contract — the empathy job owns the transaction boundary). Returns the same
    ``None`` sentinel as ``assess`` when there is not enough history.
    """
    now = now or datetime.now(timezone.utc)

    windows = await _spend_windows(db, user.id, now=now)
    if windows is None:
        return None
    current_spend, baseline_history = windows

    goal_remaining, goal_label = await _nearest_goal(db, user.id)
    avg_savings = await get_avg_monthly_savings(db, user.id, today=now.date())

    return assess(
        baseline_history,
        current_spend,
        goal_remaining=goal_remaining,
        avg_monthly_savings=avg_savings,
        goal_label=goal_label,
        threshold_pct=threshold_pct,
        absolute_floor=absolute_floor,
    )


# ---------------------------------------------------------------------
# Pure math helpers
# ---------------------------------------------------------------------


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(Decimal(v) for v in values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal(2)


def _months_to_reach(remaining: Decimal, monthly_savings: Decimal) -> int:
    """Whole months to save ``remaining`` at ``monthly_savings`` per month.

    Rounds *up*: a partial final month still counts, so a slower rate always
    reports at least as many months as a faster one — the delay we derive from
    two of these is never negative for a genuine slowdown.
    """
    if monthly_savings <= 0:
        raise ValueError("monthly_savings must be positive")
    return max(1, math.ceil(remaining / monthly_savings))


# ---------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------


async def _spend_windows(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime
) -> tuple[Decimal, list[Decimal]] | None:
    """Return ``(current_window_spend, [baseline window spends])`` or ``None``.

    The current window is the trailing 30 days; the baseline windows are the
    three 30-day windows before that. Using rolling 30-day windows (rather than
    calendar months) keeps the current window full — a partial calendar month
    would understate spend early in the month and misfire the drift check.

    Returns ``None`` when the user has no expense older than the baseline span
    (``MIN_HISTORY_WINDOWS`` × 30 days) — i.e. not enough history for a
    trustworthy baseline.
    """
    span_days = (MIN_HISTORY_WINDOWS + 1) * _WINDOW_DAYS  # current + 3 baseline
    since = (now - timedelta(days=span_days)).date()
    today = now.date()

    earliest_stmt = select(func.min(Expense.expense_date)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.transaction_type == "expense",
        Expense.category.notin_(_INTERNAL_CATEGORIES),
    )
    earliest = (await db.execute(earliest_stmt)).scalar_one_or_none()
    baseline_start = (now - timedelta(days=MIN_HISTORY_WINDOWS * _WINDOW_DAYS)).date()
    if earliest is None or earliest > baseline_start:
        return None

    stmt = select(Expense.amount, Expense.expense_date).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.transaction_type == "expense",
        Expense.expense_date >= since,
        Expense.expense_date <= today,
        Expense.category.notin_(_INTERNAL_CATEGORIES),
    )
    rows = (await db.execute(stmt)).all()

    buckets = [Decimal(0) for _ in range(MIN_HISTORY_WINDOWS + 1)]
    for amount, expense_date in rows:
        days_ago = (today - expense_date).days
        if days_ago < 0:
            continue
        idx = days_ago // _WINDOW_DAYS
        if idx <= MIN_HISTORY_WINDOWS:
            buckets[idx] += Decimal(amount or 0)

    current_spend = buckets[0]
    baseline_history = buckets[1:]
    return current_spend, baseline_history


async def _nearest_goal(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[Decimal | None, str | None]:
    """The goal whose delay we'll report: the highest-priority active goal
    that still has something left to save.

    Ordered by ``priority`` (1 = highest), then soonest ``target_date``, then
    oldest. Returns ``(remaining, name)`` for the first with ``remaining > 0``,
    else ``(None, None)`` so ``assess`` skips the Twin consequence.
    """
    stmt = (
        select(Goal)
        .where(
            Goal.user_id == user_id,
            Goal.deleted_at.is_(None),
            Goal.status == "active",
        )
        .order_by(
            Goal.priority.asc(),
            Goal.target_date.asc().nullslast(),
            Goal.created_at.asc(),
        )
    )
    for goal in (await db.execute(stmt)).scalars():
        remaining = Decimal(goal.target_amount or 0) - Decimal(goal.current_amount or 0)
        if remaining > 0:
            return remaining, goal.name
    return None, None


__all__ = [
    "DriftAssessment",
    "assess",
    "compute_drift",
    "DEFAULT_DRIFT_PCT",
    "DEFAULT_DRIFT_ABS_FLOOR",
    "MIN_HISTORY_WINDOWS",
]
