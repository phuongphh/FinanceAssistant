"""Dashboard aggregation helpers for the Telegram Mini App.

Kept separate from `report_service.py` (which generates monthly
LLM-authored narratives) because the dashboard needs cheap,
cache-friendly reads that run on every page load.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.user import User

# Legacy category codes (from early phases) → the shared config codes.
_CATEGORY_CODE_ALIASES = {
    "food_drink": "food",
    "utilities": "utility",
    "savings": "saving",
    "needs_review": "other",
}


def _normalize_category(code: str | None) -> str:
    if not code:
        return "other"
    return _CATEGORY_CODE_ALIASES.get(code, code)


def current_month_key(today: date | None = None) -> str:
    return (today or date.today()).strftime("%Y-%m")


async def get_user_by_telegram_id(
    db: AsyncSession, telegram_id: int
) -> User | None:
    stmt = select(User).where(
        User.telegram_id == telegram_id,
        User.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_or_create_user(
    db: AsyncSession,
    telegram_id: int,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
) -> tuple[User, bool]:
    """Return (user, created). Creates a DB record on first encounter."""
    user = await get_user_by_telegram_id(db, telegram_id)
    if user:
        return user, False
    user = User(
        telegram_id=telegram_id,
        telegram_handle=username,
        display_name=first_name or last_name,
    )
    db.add(user)
    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    # flush() populates user.id from the DB default without ending the tx.
    await db.flush()
    await db.refresh(user)
    return user, True


async def get_month_total(
    db: AsyncSession, user_id: uuid.UUID, month_key: str | None = None
) -> float:
    month_key = month_key or current_month_key()
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.month_key == month_key,
        Expense.deleted_at.is_(None),
    )
    total = (await db.execute(stmt)).scalar_one()
    return float(total or 0)


async def get_month_transaction_count(
    db: AsyncSession, user_id: uuid.UUID, month_key: str | None = None
) -> int:
    month_key = month_key or current_month_key()
    stmt = select(func.count()).where(
        Expense.user_id == user_id,
        Expense.month_key == month_key,
        Expense.deleted_at.is_(None),
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def get_category_breakdown(
    db: AsyncSession, user_id: uuid.UUID, month_key: str | None = None
) -> list[dict]:
    """Trả về breakdown đã kèm emoji/color sẵn để frontend không tính lại."""
    from backend.config.categories import get_category

    month_key = month_key or current_month_key()
    stmt = (
        select(
            Expense.category,
            func.sum(Expense.amount).label("total"),
        )
        .where(
            Expense.user_id == user_id,
            Expense.month_key == month_key,
            Expense.deleted_at.is_(None),
        )
        .group_by(Expense.category)
    )
    rows = (await db.execute(stmt)).all()

    # Gộp các category_code sau normalize (food_drink + food → food)
    totals: dict[str, float] = {}
    for row in rows:
        key = _normalize_category(row.category)
        totals[key] = totals.get(key, 0.0) + float(row.total or 0)

    breakdown = []
    for code, amount in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
        cat = get_category(code)
        breakdown.append(
            {
                "code": cat.code,
                "name": cat.name_vi,
                "emoji": cat.emoji,
                "color": cat.color_hex,
                "amount": amount,
            }
        )
    return breakdown


async def get_daily_trend(
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int = 30,
    end: date | None = None,
) -> list[dict]:
    """Daily expense total for the last `days` days, zero-filled."""
    end_date = end or date.today()
    start_date = end_date - timedelta(days=days - 1)

    stmt = (
        select(
            Expense.expense_date.label("day"),
            func.sum(Expense.amount).label("total"),
        )
        .where(
            Expense.user_id == user_id,
            Expense.expense_date >= start_date,
            Expense.expense_date <= end_date,
            Expense.deleted_at.is_(None),
        )
        .group_by(Expense.expense_date)
    )
    rows = (await db.execute(stmt)).all()
    by_day = {row.day: float(row.total or 0) for row in rows}

    trend = []
    current = start_date
    while current <= end_date:
        trend.append(
            {"date": current.isoformat(), "amount": by_day.get(current, 0.0)}
        )
        current += timedelta(days=1)
    return trend


async def get_recent_transactions(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 20
) -> list[dict]:
    from backend.config.categories import get_category

    stmt = (
        select(Expense)
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
        )
        .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    out = []
    for e in rows:
        cat = get_category(_normalize_category(e.category))
        out.append(
            {
                "id": str(e.id),
                "merchant": e.merchant or e.note,
                "amount": float(e.amount),
                "category": {
                    "code": cat.code,
                    "name": cat.name_vi,
                    "emoji": cat.emoji,
                    "color": cat.color_hex,
                },
                "date": e.expense_date.isoformat(),
            }
        )
    return out
