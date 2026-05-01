"""Handlers for ``query_expenses`` and ``query_expenses_by_category``.

Backed by the V1 ``expenses`` table via ``expense_service`` — the
``transactions`` rename in CLAUDE.md is still pending so we adapt to
what exists today. When that migration lands, swap the import; nothing
in the handler needs to change.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.config.categories import get_category
from backend.intent.extractors.time_range import TimeRange, extract as extract_time_range
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.expense import Expense
from backend.models.user import User

# Top transactions to include in the per-period listing. Beyond this we
# print "...và X giao dịch nhỏ hơn".
_TOP_N_TRANSACTIONS = 10


def _resolve_time_range(intent: IntentResult) -> TimeRange:
    """Return the time range from the intent params or default to this month."""
    label = intent.parameters.get("time_range")
    if label:
        # Re-derive dates from the label so we don't need to pass dates
        # through the parameters dict (label is JSON-friendly; date
        # objects aren't).
        tr = _label_to_range(label)
        if tr is not None:
            return tr
    # Fallback: parse the raw text once more, defaulting to this month.
    tr = extract_time_range(intent.raw_text or "")
    if tr is not None:
        return tr
    today = date.today()
    return TimeRange(today.replace(day=1), today, "this_month")


def _label_to_range(label: str) -> TimeRange | None:
    """Best-effort re-derive of a TimeRange from its stable label."""
    needle = {
        "today": "hôm nay",
        "yesterday": "hôm qua",
        "this_week": "tuần này",
        "last_week": "tuần trước",
        "this_month": "tháng này",
        "last_month": "tháng trước",
        "this_year": "năm nay",
        "last_year": "năm ngoái",
    }.get(label)
    if needle is None:
        return None
    return extract_time_range(needle)


_TIME_LABELS_VI = {
    "today": "hôm nay",
    "yesterday": "hôm qua",
    "this_week": "tuần này",
    "last_week": "tuần trước",
    "this_month": "tháng này",
    "last_month": "tháng trước",
    "this_year": "năm nay",
    "last_year": "năm ngoái",
}


async def _fetch_expenses(
    db: AsyncSession,
    user: User,
    *,
    start: date,
    end: date,
    category: str | None = None,
) -> list[Expense]:
    stmt = select(Expense).where(
        Expense.user_id == user.id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= start,
        Expense.expense_date <= end,
    )
    if category:
        stmt = stmt.where(Expense.category == category)
    stmt = stmt.order_by(Expense.amount.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


def _format_listing(
    expenses: list[Expense],
    *,
    time_range: TimeRange,
    user: User,
    category: str | None = None,
) -> str:
    total = sum(Decimal(tx.amount or 0) for tx in expenses)
    count = len(expenses)
    label_vi = _TIME_LABELS_VI.get(time_range.label, time_range.label)

    if category:
        cat_obj = get_category(category)
        header = f"💸 Chi {cat_obj.emoji} *{cat_obj.name_vi}* {label_vi}:"
    else:
        header = f"💸 Chi tiêu {label_vi}:"

    lines = [
        header,
        "━━━━━━━━━━━━━━━━━━━━",
        f"Tổng: *{format_money_full(total)}* ({count} giao dịch)",
        "",
    ]
    top = sorted(expenses, key=lambda x: Decimal(x.amount or 0), reverse=True)[
        :_TOP_N_TRANSACTIONS
    ]
    for tx in top:
        cat_obj = get_category(tx.category or "other")
        merchant = tx.merchant or "N/A"
        lines.append(
            f"{cat_obj.emoji} {merchant} — {format_money_short(tx.amount)}"
        )
    if count > _TOP_N_TRANSACTIONS:
        lines.append("")
        lines.append(f"_...và {count - _TOP_N_TRANSACTIONS} giao dịch nhỏ hơn_")
    return "\n".join(lines)


def _empty_message(
    *, time_range: TimeRange, user: User, category: str | None = None
) -> str:
    name = user.display_name or "bạn"
    label_vi = _TIME_LABELS_VI.get(time_range.label, time_range.label)
    if category:
        cat_obj = get_category(category)
        return (
            f"{name} không có chi tiêu cho {cat_obj.emoji} {cat_obj.name_vi} "
            f"{label_vi} 🌱"
        )
    return f"{name} không có chi tiêu nào {label_vi}!"


class QueryExpensesHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        time_range = _resolve_time_range(intent)
        expenses = await _fetch_expenses(
            db, user, start=time_range.start, end=time_range.end
        )
        if not expenses:
            return _empty_message(time_range=time_range, user=user)
        return _format_listing(
            expenses, time_range=time_range, user=user
        )


class QueryExpensesByCategoryHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        time_range = _resolve_time_range(intent)
        category = intent.parameters.get("category")
        if not category:
            # Without a category, behave like the general handler so the
            # user still gets useful data instead of "I don't know".
            expenses = await _fetch_expenses(
                db, user, start=time_range.start, end=time_range.end
            )
            if not expenses:
                return _empty_message(time_range=time_range, user=user)
            return _format_listing(
                expenses, time_range=time_range, user=user
            )

        expenses = await _fetch_expenses(
            db,
            user,
            start=time_range.start,
            end=time_range.end,
            category=category,
        )
        if not expenses:
            return _empty_message(
                time_range=time_range, user=user, category=category
            )
        return _format_listing(
            expenses, time_range=time_range, user=user, category=category
        )
