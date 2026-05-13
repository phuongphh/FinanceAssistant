"""``compute_metric`` tool — single-number derived facts.

Each metric lives in a small pure function so they're testable and
the LLM-facing tool stays a thin dispatcher. We deliberately avoid
sharing state between metrics: the ``compute_*`` helpers each open
their own queries, take what they need, return ``MetricResult``.

Why pure functions instead of e.g. a strategy class hierarchy:
metrics are tiny (≤30 lines each), share no state, and a flat
dispatch keeps the call graph obvious to the LLM. Adding a new
metric = add one helper + one MetricName entry.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.schemas import (
    ComputeMetricInput,
    MetricName,
    MetricResult,
)
from backend.models.expense import Expense
from backend.models.income_record import IncomeRecord
from backend.models.user import User
from backend.wealth.models.asset import Asset
from backend.wealth.services import net_worth_calculator


@dataclass
class _Window:
    start: date
    end: date

    @property
    def label(self) -> str:
        if self.start == self.end:
            return self.start.isoformat()
        return f"{self.start.isoformat()}..{self.end.isoformat()}"


def _window(months: int | None, default: int) -> _Window:
    """Build a ``[today - months, today]`` window."""
    end = date.today()
    span = months if months is not None else default
    start = end - timedelta(days=30 * span)
    return _Window(start=start, end=end)


# ---------------------------------------------------------------------------
# Metric implementations
# ---------------------------------------------------------------------------


async def _expenses_in_window(
    db: AsyncSession, user_id: uuid.UUID, w: _Window
) -> Decimal:
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= w.start,
        Expense.expense_date <= w.end,
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _income_in_window(
    db: AsyncSession,
    user_id: uuid.UUID,
    w: _Window,
    user_monthly_fallback: Decimal,
) -> Decimal:
    """Income for the window, falling back to ``users.monthly_income``
    pro-rated by month-count when no IncomeRecord rows exist.

    The fallback matters because Phase 3.5 users were tracked via
    ``monthly_income`` only — without it, "saving rate" reads as 100%
    after first launch."""
    stmt = select(func.coalesce(func.sum(IncomeRecord.amount), 0)).where(
        IncomeRecord.user_id == user_id,
        IncomeRecord.deleted_at.is_(None),
        IncomeRecord.period >= w.start,
        IncomeRecord.period <= w.end,
    )
    recorded = Decimal((await db.execute(stmt)).scalar() or 0)
    if recorded > 0:
        return recorded

    if user_monthly_fallback <= 0:
        return Decimal(0)
    months = max(1, round((w.end - w.start).days / 30))
    return user_monthly_fallback * months


async def compute_saving_rate(
    db: AsyncSession, user: User, period_months: int | None
) -> MetricResult:
    """`(income - expense) / income` — always returns a percentage."""
    w = _window(period_months, default=1)
    income = await _income_in_window(
        db, user.id, w, Decimal(user.monthly_income or 0)
    )
    expense = await _expenses_in_window(db, user.id, w)
    if income <= 0:
        return MetricResult(
            metric_name=MetricName.SAVING_RATE.value,
            value=0.0,
            unit="percent",
            period=w.label,
            context="Chưa có dữ liệu thu nhập để tính.",
        )
    rate = float((income - expense) / income * 100)
    return MetricResult(
        metric_name=MetricName.SAVING_RATE.value,
        value=round(rate, 2),
        unit="percent",
        period=w.label,
        context=f"Thu nhập {income:,.0f}đ – chi {expense:,.0f}đ.",
    )


async def compute_net_worth_growth(
    db: AsyncSession, user: User, period_months: int | None
) -> MetricResult:
    """% change in net worth across the window. ``Decimal`` math."""
    w = _window(period_months, default=12)
    current = await net_worth_calculator.calculate(db, user.id)
    past = await net_worth_calculator.calculate_historical(db, user.id, w.start)
    if past <= 0:
        return MetricResult(
            metric_name=MetricName.NET_WORTH_GROWTH.value,
            value=0.0,
            unit="percent",
            period=w.label,
            context="Chưa có snapshot tài sản đủ xa để so sánh.",
        )
    pct = float((current.total - past) / past * 100)
    return MetricResult(
        metric_name=MetricName.NET_WORTH_GROWTH.value,
        value=round(pct, 2),
        unit="percent",
        period=w.label,
        context=f"{past:,.0f}đ → {current.total:,.0f}đ.",
    )


async def compute_portfolio_total_gain(
    db: AsyncSession, user: User, period_months: int | None  # ignored
) -> MetricResult:
    """Sum of ``current_value − initial_value`` across all active assets.

    period_months is ignored — this is an inception-to-date PnL,
    matching how users phrase "tổng lãi portfolio"."""
    stmt = select(
        func.coalesce(func.sum(Asset.current_value - Asset.initial_value), 0),
        func.coalesce(func.sum(Asset.initial_value), 0),
    ).where(Asset.user_id == user.id, Asset.is_active.is_(True))
    row = (await db.execute(stmt)).one()
    gain = Decimal(row[0] or 0)
    cost = Decimal(row[1] or 0)
    pct = float(gain / cost * 100) if cost > 0 else 0.0
    return MetricResult(
        metric_name=MetricName.PORTFOLIO_TOTAL_GAIN.value,
        value=float(gain),
        unit="vnd",
        period="inception_to_date",
        context=f"Tổng vốn gốc {cost:,.0f}đ, gain {pct:+.2f}%.",
    )


async def compute_portfolio_total_gain_pct(
    db: AsyncSession, user: User, period_months: int | None
) -> MetricResult:
    res = await compute_portfolio_total_gain(db, user, period_months)
    # context line embeds "%"; we extract from cost basis cleanly
    stmt = select(
        func.coalesce(func.sum(Asset.current_value - Asset.initial_value), 0),
        func.coalesce(func.sum(Asset.initial_value), 0),
    ).where(Asset.user_id == user.id, Asset.is_active.is_(True))
    row = (await db.execute(stmt)).one()
    gain = Decimal(row[0] or 0)
    cost = Decimal(row[1] or 0)
    pct = float(gain / cost * 100) if cost > 0 else 0.0
    return MetricResult(
        metric_name=MetricName.PORTFOLIO_TOTAL_GAIN_PCT.value,
        value=round(pct, 2),
        unit="percent",
        period="inception_to_date",
        context=res.context,
    )


async def compute_average_monthly_expense(
    db: AsyncSession, user: User, period_months: int | None
) -> MetricResult:
    months = period_months if period_months is not None else 3
    w = _window(months, default=3)
    total = await _expenses_in_window(db, user.id, w)
    avg = float(total / months) if months > 0 else 0.0
    return MetricResult(
        metric_name=MetricName.AVERAGE_MONTHLY_EXPENSE.value,
        value=round(avg, 0),
        unit="vnd",
        period=w.label,
        context=f"Tổng {total:,.0f}đ chia {months} tháng.",
    )


async def compute_expense_to_income_ratio(
    db: AsyncSession, user: User, period_months: int | None
) -> MetricResult:
    w = _window(period_months, default=1)
    income = await _income_in_window(
        db, user.id, w, Decimal(user.monthly_income or 0)
    )
    expense = await _expenses_in_window(db, user.id, w)
    if income <= 0:
        return MetricResult(
            metric_name=MetricName.EXPENSE_TO_INCOME_RATIO.value,
            value=0.0,
            unit="percent",
            period=w.label,
            context="Chưa có dữ liệu thu nhập.",
        )
    pct = float(expense / income * 100)
    return MetricResult(
        metric_name=MetricName.EXPENSE_TO_INCOME_RATIO.value,
        value=round(pct, 2),
        unit="percent",
        period=w.label,
        context=f"Chi {expense:,.0f}đ / Thu {income:,.0f}đ.",
    )


async def compute_diversification_score(
    db: AsyncSession, user: User, period_months: int | None  # ignored
) -> MetricResult:
    """Herfindahl-style score: 100 = perfectly diversified across the
    six asset classes; 0 = single class.

    Score = (1 − HHI) × 100 where HHI = Σ (share_i)². The "perfect
    diversification" reference is six classes (the canonical bucket
    list) so a single-asset portfolio scores 0 and equal-weighted
    six-class scores ≈83 (1 − 6×(1/6)² = 5/6)."""
    breakdown = await net_worth_calculator.calculate(db, user.id)
    total = breakdown.total
    if total <= 0:
        return MetricResult(
            metric_name=MetricName.DIVERSIFICATION_SCORE.value,
            value=0.0,
            unit="score",
            period="current",
            context="Chưa có tài sản để tính.",
        )
    hhi = Decimal(0)
    for v in breakdown.by_type.values():
        share = v / total
        hhi += share * share
    score = float((Decimal(1) - hhi) * 100)
    return MetricResult(
        metric_name=MetricName.DIVERSIFICATION_SCORE.value,
        value=round(score, 1),
        unit="score",
        period="current",
        context=f"{len(breakdown.by_type)} loại tài sản.",
    )


_DISPATCH = {
    MetricName.SAVING_RATE: compute_saving_rate,
    MetricName.NET_WORTH_GROWTH: compute_net_worth_growth,
    MetricName.PORTFOLIO_TOTAL_GAIN: compute_portfolio_total_gain,
    MetricName.PORTFOLIO_TOTAL_GAIN_PCT: compute_portfolio_total_gain_pct,
    MetricName.AVERAGE_MONTHLY_EXPENSE: compute_average_monthly_expense,
    MetricName.EXPENSE_TO_INCOME_RATIO: compute_expense_to_income_ratio,
    MetricName.DIVERSIFICATION_SCORE: compute_diversification_score,
}


# ---------------------------------------------------------------------------
# Tool wrapper
# ---------------------------------------------------------------------------


class ComputeMetricTool(Tool):
    @property
    def name(self) -> str:
        return "compute_metric"

    @property
    def description(self) -> str:
        return (
            "Compute a single financial metric for the user. Returns "
            "value + unit + a short context string.\n"
            "\n"
            "Metrics:\n"
            "- saving_rate: % income kept after expenses (default 1 month).\n"
            "- net_worth_growth: % net worth change over period_months "
            "(default 12).\n"
            "- portfolio_total_gain: VND PnL across all active assets.\n"
            "- portfolio_total_gain_pct: % PnL across all active assets.\n"
            "- average_monthly_expense: avg VND/month over period_months "
            "(default 3).\n"
            "- expense_to_income_ratio: % income consumed by expenses.\n"
            "- diversification_score: 0-100, higher = better diversified.\n"
            "\n"
            "Examples:\n"
            "- 'tỷ lệ tiết kiệm tháng này' → metric_name=saving_rate, "
            "period_months=1\n"
            "- 'tổng lãi portfolio' → metric_name=portfolio_total_gain\n"
            "- 'chi trung bình 6 tháng qua' → "
            "metric_name=average_monthly_expense, period_months=6"
        )

    @property
    def input_schema(self) -> Type:
        return ComputeMetricInput

    @property
    def output_schema(self) -> Type:
        return MetricResult

    async def execute(
        self,
        input_data: ComputeMetricInput,
        user: User,
        db: AsyncSession,
    ) -> MetricResult:
        impl = _DISPATCH[input_data.metric_name]
        return await impl(db, user, input_data.period_months)
