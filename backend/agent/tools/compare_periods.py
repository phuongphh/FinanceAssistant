"""``compare_periods`` tool — A vs B for a single metric."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.schemas import (
    CompareMetric,
    ComparePeriod,
    ComparePeriodsInput,
    ComparisonResult,
)
from backend.models.expense import Expense
from backend.models.income_record import IncomeRecord
from backend.models.user import User
from backend.wealth.services import net_worth_calculator

_PERIOD_LABELS_VI = {
    ComparePeriod.THIS_MONTH: "tháng này",
    ComparePeriod.LAST_MONTH: "tháng trước",
    ComparePeriod.THIS_YEAR: "năm nay",
    ComparePeriod.LAST_YEAR: "năm trước",
}


def _period_bounds(p: ComparePeriod, today: date | None = None) -> tuple[date, date]:
    """Map a ``ComparePeriod`` to (start_inclusive, end_inclusive).

    "this_month" runs from day 1 of the current month to today —
    not month-end — because comparing partial-month-vs-full-month is
    what users actually mean ("đã chi tháng này so với tháng trước").
    "last_month" is the full prior calendar month."""
    today = today or date.today()
    if p is ComparePeriod.THIS_MONTH:
        start = today.replace(day=1)
        return start, today
    if p is ComparePeriod.LAST_MONTH:
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start, last_month_end
    if p is ComparePeriod.THIS_YEAR:
        return today.replace(month=1, day=1), today
    if p is ComparePeriod.LAST_YEAR:
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    raise ValueError(f"Unknown period {p}")


# ---------------------------------------------------------------------------
# metric implementations
# ---------------------------------------------------------------------------


async def _expenses(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> Decimal:
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= start,
        Expense.expense_date <= end,
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _income(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> Decimal:
    stmt = select(func.coalesce(func.sum(IncomeRecord.amount), 0)).where(
        IncomeRecord.user_id == user_id,
        IncomeRecord.deleted_at.is_(None),
        IncomeRecord.period >= start,
        IncomeRecord.period <= end,
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _net_worth(
    db: AsyncSession, user_id: uuid.UUID, end: date
) -> Decimal:
    """Net worth at end-of-period uses ``calculate_historical`` —
    answers 'how much did I have on Apr 30' rather than today."""
    return await net_worth_calculator.calculate_historical(db, user_id, end)


async def _savings(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> Decimal:
    income = await _income(db, user_id, start, end)
    expense = await _expenses(db, user_id, start, end)
    return income - expense


_DISPATCH = {
    CompareMetric.EXPENSES: _expenses,
    CompareMetric.INCOME: _income,
    CompareMetric.SAVINGS: _savings,
}


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class ComparePeriodsTool(Tool):
    @property
    def name(self) -> str:
        return "compare_periods"

    @property
    def description(self) -> str:
        return (
            "Compare a single metric (expenses / income / net_worth / "
            "savings) across two named periods.\n"
            "\n"
            "Examples:\n"
            "- 'chi tháng này so với tháng trước' → "
            "metric=expenses, period_a=this_month, period_b=last_month\n"
            "- 'thu nhập năm nay vs năm trước' → "
            "metric=income, period_a=this_year, period_b=last_year\n"
            "- 'net worth tháng này so với tháng trước' → "
            "metric=net_worth, period_a=this_month, period_b=last_month\n"
            "Returns absolute + percent diff."
        )

    @property
    def input_schema(self) -> Type:
        return ComparePeriodsInput

    @property
    def output_schema(self) -> Type:
        return ComparisonResult

    async def execute(
        self,
        input_data: ComparePeriodsInput,
        user: User,
        db: AsyncSession,
    ) -> ComparisonResult:
        a_start, a_end = _period_bounds(input_data.period_a)
        b_start, b_end = _period_bounds(input_data.period_b)

        if input_data.metric is CompareMetric.NET_WORTH:
            value_a = await _net_worth(db, user.id, a_end)
            value_b = await _net_worth(db, user.id, b_end)
        else:
            fn = _DISPATCH[input_data.metric]
            value_a = await fn(db, user.id, a_start, a_end)
            value_b = await fn(db, user.id, b_start, b_end)

        diff = value_a - value_b
        # Reference for percent is period_b (the "previous" baseline).
        # When B is zero we emit 0 rather than ±inf — the absolute
        # diff already conveys "everything new this period".
        pct = float(diff / value_b * 100) if value_b != 0 else 0.0
        return ComparisonResult(
            metric=input_data.metric.value,
            period_a_value=value_a,
            period_b_value=value_b,
            diff_absolute=diff,
            diff_percent=round(pct, 2),
            period_a_label=_PERIOD_LABELS_VI[input_data.period_a],
            period_b_label=_PERIOD_LABELS_VI[input_data.period_b],
        )
