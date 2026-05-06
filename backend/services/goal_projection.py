"""Goal projection + feasibility analysis — Phase 3.8 Epic 5 (S14).

Spec methodology (per § P3.8-S14):

For each goal:
  remaining = target_amount − current_amount
  current_progress_pct = current / target × 100

If ``target_date`` is set:
  months_remaining = months between today and target_date
  required_monthly_savings = remaining / months_remaining
  feasibility = compare(required, actual_avg_monthly_savings)

If ``target_date`` is open-ended AND user has positive savings:
  estimated_completion_months = remaining / actual_avg_monthly_savings
  estimated_completion_date = today + estimated_completion_months

Feasibility bands (spec):
  required ≤ 0.5 × actual    → easy           (2x+ buffer)
  0.5 < ratio ≤ 1.0          → feasible       (current rate is enough)
  1.0 < ratio ≤ 1.5          → stretch        (need +50%)
  1.5 < ratio ≤ 2.0          → ambitious      (need 2×)
  ratio > 2.0                → needs_revision (unrealistic)

Average monthly savings comes from a 3-month historical proxy:
  est_monthly_income = sum(active stream.monthly_equivalent)
  avg_monthly_expense = total expenses last 3 months / 3
  avg_monthly_savings = max(0, income − expense)

We don't use ``cashflow_forecaster.forecast`` because that *adds*
recurring patterns on top of ambient — fine for forecasting but
double-counts when measuring the user's *historical* saving rate.

Layer contract: pure read; no DB writes. Caller persists the cache
on Goal.monthly_savings_required separately if it wants to.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.schemas.goal import FeasibilityBand, GoalProjection
from backend.wealth.models.income_stream import IncomeStream


HISTORY_MONTHS = 3      # baseline window for actual saving-rate proxy
DEFICIT_FLOOR_NOTE = (
    "Hiện tại chi nhiều hơn thu — cần cải thiện dòng tiền trước khi "
    "đặt deadline cho mục tiêu này."
)


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------


async def project_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID,
    *, today: date | None = None,
) -> GoalProjection | None:
    """Project a single goal. Returns ``None`` if the goal isn't
    owned by ``user_id`` (mirror of ``goal_service.get_goal``)."""
    goal = await _get_goal(db, user_id, goal_id)
    if goal is None:
        return None
    today = today or date.today()
    avg_savings = await get_avg_monthly_savings(db, user_id, today=today)
    return _project(goal, avg_savings, today=today)


def project_goal_with_savings(
    goal: Goal,
    avg_monthly_savings: Decimal,
    *,
    today: date | None = None,
) -> GoalProjection:
    """Pure variant — doesn't touch the DB. Used by the wizard's
    inline "preview" step where we have the goal payload in hand
    plus a single avg-savings query.
    """
    return _project(goal, avg_monthly_savings, today=today or date.today())


async def get_avg_monthly_savings(
    db: AsyncSession, user_id: uuid.UUID, *, today: date | None = None,
) -> Decimal:
    """Estimate ``income − expense`` per month, averaged over the
    last 3 months.

    Income from streams (no per-receipt log exists yet; streams
    are the canonical "what comes in"). Expense from the actual
    transaction log. Floor at 0 — negative savings = "currently
    losing money" which the projection layer flags via a note,
    rather than producing nonsense feasibility ratios.
    """
    today = today or date.today()
    income = await _monthly_income_from_streams(db, user_id)
    expense = await _avg_monthly_expense(db, user_id, today=today)
    savings = income - expense
    return savings if savings > 0 else Decimal(0)


# ---------------------------------------------------------------------
# Core projection logic
# ---------------------------------------------------------------------


def _project(
    goal: Goal, avg_savings: Decimal, *, today: date,
) -> GoalProjection:
    target = Decimal(goal.target_amount or 0)
    current = Decimal(goal.current_amount or 0)
    remaining = target - current
    progress_pct = float(current / target * Decimal(100)) if target > 0 else 0.0

    notes: list[str] = []
    months_remaining: Optional[int] = None
    required: Optional[Decimal] = None
    feasibility: Optional[FeasibilityBand] = None
    estimated_months: Optional[float] = None
    estimated_date: Optional[date] = None

    # If already completed (or ahead of target), short-circuit with
    # a cheerful note instead of a deficit warning.
    if remaining <= 0:
        notes.append("✅ Đã đạt mục tiêu — chúc mừng!")
        return GoalProjection(
            goal_id=goal.id,
            remaining_amount=Decimal(0),
            current_progress_pct=min(progress_pct, 100.0),
            avg_monthly_savings=avg_savings if avg_savings > 0 else None,
            notes=notes,
        )

    if goal.target_date is not None and goal.target_date > today:
        months_remaining = _months_between(today, goal.target_date)
        if months_remaining > 0:
            required = (remaining / Decimal(months_remaining)).quantize(
                Decimal("1")
            )
            feasibility = _assess_feasibility(required, avg_savings)
            notes.extend(_supportive_notes(feasibility, required, avg_savings))

    elif goal.target_date is None:
        # Open-ended goal: project completion *if* the user keeps
        # their current saving rate.
        if avg_savings > 0:
            ratio = remaining / avg_savings
            estimated_months = float(ratio)
            estimated_date = _add_months_approx(today, estimated_months)
        else:
            notes.append(
                "Chưa đủ dữ liệu dòng tiền — thêm lịch sử để mình "
                "ước tính được."
            )

    elif goal.target_date is not None and goal.target_date <= today:
        # Past-due — still a valid goal (user might be a bit late
        # but determined). Frame supportively: required savings
        # collapses into "lump sum needed now".
        notes.append(
            f"Hạn đã qua ({goal.target_date.isoformat()}) — "
            f"vẫn còn cần {int(remaining):,}đ. Đặt deadline mới?"
        )

    return GoalProjection(
        goal_id=goal.id,
        remaining_amount=remaining,
        current_progress_pct=min(progress_pct, 100.0),
        months_remaining=months_remaining,
        required_monthly_savings=required,
        feasibility=feasibility,
        avg_monthly_savings=avg_savings if avg_savings > 0 else None,
        estimated_completion_months=estimated_months,
        estimated_completion_date=estimated_date,
        notes=notes,
    )


def _assess_feasibility(
    required: Decimal, actual: Decimal,
) -> FeasibilityBand:
    """Classification per spec § P3.8-S14.

    ``actual ≤ 0`` → ``UNKNOWN`` (we can't divide; flag for the
    user that we lack data rather than silently surfacing
    'needs_revision' which would be misleading).
    """
    if actual <= 0:
        return FeasibilityBand.UNKNOWN
    ratio = float(required / actual) if actual > 0 else float("inf")
    if ratio <= 0.5:
        return FeasibilityBand.EASY
    if ratio <= 1.0:
        return FeasibilityBand.FEASIBLE
    if ratio <= 1.5:
        return FeasibilityBand.STRETCH
    if ratio <= 2.0:
        return FeasibilityBand.AMBITIOUS
    return FeasibilityBand.NEEDS_REVISION


def _supportive_notes(
    band: FeasibilityBand,
    required: Decimal,
    actual: Decimal,
) -> list[str]:
    """Spec § P3.8-S14: 'never use harsh language, always offer
    alternatives'. We surface concrete options rather than
    judgement.
    """
    if band == FeasibilityBand.UNKNOWN:
        return [
            "Mình chưa biết tỷ lệ tiết kiệm hiện tại của bạn. "
            "Thêm thu nhập + lịch sử chi tiêu để mình tính chính xác hơn."
        ]
    if band == FeasibilityBand.EASY:
        return [
            "Mục tiêu này dư sức — bạn còn nhiều buffer để dồn vào "
            "mục tiêu khác hoặc đầu tư."
        ]
    if band == FeasibilityBand.FEASIBLE:
        return [
            "Với mức tiết kiệm hiện tại, bạn đạt được mục tiêu này "
            "đúng hạn 👍"
        ]
    if band == FeasibilityBand.STRETCH:
        return [
            "Hơi thử thách — cần tăng saving rate ~50% so với hiện tại.",
            "Lựa chọn: lùi deadline, giảm target, hoặc tăng thu nhập.",
        ]
    if band == FeasibilityBand.AMBITIOUS:
        return [
            "Mục tiêu khá tham vọng — cần 2× saving rate hiện tại.",
            "Cân nhắc: lùi deadline, giảm target, hoặc kết hợp 2 cái.",
        ]
    # NEEDS_REVISION
    return [
        "Khó đạt với rate hiện tại 🤔",
        f"Để khả thi: cần thêm {_format_money(required - actual)}/tháng "
        "(hoặc lùi deadline xa hơn).",
        "Mục tiêu lớn vẫn ý nghĩa — chia nhỏ thành mốc trung gian "
        "giúp duy trì động lực.",
    ]


def _format_money(amount: Decimal) -> str:
    """Tiny formatter for the supportive-notes path. The full
    ``format_money_short`` lives in ``backend.bot.formatters.money``
    but we don't want a model→formatters import cycle, so this
    handles the only case (positive whole-VND amount in tr/k)."""
    abs_amt = abs(amount)
    if abs_amt >= Decimal("1_000_000_000"):
        return f"{abs_amt / Decimal('1_000_000_000'):.1f} tỷ"
    if abs_amt >= Decimal("1_000_000"):
        return f"{abs_amt / Decimal('1_000_000'):.0f}tr"
    if abs_amt >= Decimal("1_000"):
        return f"{abs_amt / Decimal('1_000'):.0f}k"
    return f"{int(abs_amt):,}đ"


def _months_between(start: date, end: date) -> int:
    """Whole-month count between two dates. Rounds toward 0 — a
    1.7-month gap returns 1 so ``required / months_remaining``
    overestimates the monthly need (safe-side error)."""
    if end <= start:
        return 0
    days = (end - start).days
    # 30.44 = avg days per month; floor to int so partial months
    # don't inflate the available timeline.
    return max(1, int(days / 30.44))


def _add_months_approx(start: date, months: float) -> date:
    """Add a fractional number of months to a date. Used only for
    the open-ended projection's ``estimated_completion_date`` —
    not financially exact (months aren't all 30 days), but the
    user reads this as "around X" so 30.44-day approximation is
    fine."""
    days = int(round(months * 30.44))
    return start + timedelta(days=days)


# ---------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------


async def _get_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID,
) -> Goal | None:
    stmt = select(Goal).where(
        Goal.id == goal_id,
        Goal.user_id == user_id,
        Goal.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _monthly_income_from_streams(
    db: AsyncSession, user_id: uuid.UUID,
) -> Decimal:
    stmt = select(IncomeStream).where(
        IncomeStream.user_id == user_id,
        IncomeStream.is_active.is_(True),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return sum((s.monthly_equivalent for s in rows), Decimal(0))


async def _avg_monthly_expense(
    db: AsyncSession, user_id: uuid.UUID, *, today: date,
) -> Decimal:
    """Average over the last ``HISTORY_MONTHS`` calendar months."""
    period_start = date(today.year, today.month, 1) - timedelta(
        days=HISTORY_MONTHS * 31,
    )
    stmt = select(Expense).where(
        Expense.user_id == user_id,
        Expense.expense_date >= period_start,
        Expense.expense_date < date(today.year, today.month, 1),
        Expense.deleted_at.is_(None),
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        return Decimal(0)
    distinct_months = {(e.expense_date.year, e.expense_date.month) for e in rows}
    months = max(len(distinct_months), 1)
    total = sum((Decimal(e.amount or 0) for e in rows), Decimal(0))
    return (total / Decimal(months)).quantize(Decimal("1"))
