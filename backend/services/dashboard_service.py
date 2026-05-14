"""Dashboard aggregation helpers for the Telegram Mini App.

Kept separate from `report_service.py` (which generates monthly
LLM-authored narratives) because the dashboard needs cheap,
cache-friendly reads that run on every page load.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import event, func, select
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


# Key into ``AsyncSession.info`` for the per-session telegram_id → User
# cache. The worker opens one session per Telegram update, so this gives
# us a request-scoped cache that's discarded on session close — no
# cross-request leakage, no manual invalidation. SQLAlchemy's identity
# map only dedups primary-key lookups, so without this each repeated
# ``get_user_by_telegram_id`` call (telegram_worker hits it 3-4× per
# callback) issued a fresh wide SELECT.
_USER_BY_TELEGRAM_ID_CACHE_KEY = "_user_by_telegram_id_cache"
_ROLLBACK_LISTENER_INSTALLED_KEY = "_user_cache_rollback_listener"


def _get_or_init_user_cache(db: AsyncSession) -> dict:
    """Return the session-scoped telegram_id→User cache, installing a
    rollback listener on first use.

    After ``db.rollback()`` SQLAlchemy expires attributes on every ORM
    instance in the session — accessing ``user.id`` on a previously
    cached instance would then trigger a lazy refresh, which raises
    ``MissingGreenlet`` in async code (see degraded paths in
    ``profile_menu.handle_profile_view``). Dropping our cache on
    ``after_rollback`` forces the next call to re-query, returning a
    fresh, non-expired instance.
    """
    info = db.info
    if _ROLLBACK_LISTENER_INSTALLED_KEY not in info:
        # Mark first so a registration failure (e.g. test doubles whose
        # ``sync_session`` isn't a real SQLAlchemy Session) doesn't loop.
        info[_ROLLBACK_LISTENER_INSTALLED_KEY] = True
        sync_session = getattr(db, "sync_session", None)
        if sync_session is not None:
            try:
                @event.listens_for(sync_session, "after_rollback")
                def _drop_cache_on_rollback(session):  # pragma: no cover - tiny shim
                    session.info.pop(_USER_BY_TELEGRAM_ID_CACHE_KEY, None)
            except Exception:
                # Event hook is purely defensive — if the underlying
                # target doesn't accept listeners, the cache still works
                # correctly within a single non-rollback flow.
                pass
    return info.setdefault(_USER_BY_TELEGRAM_ID_CACHE_KEY, {})


async def get_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> User | None:
    cache = _get_or_init_user_cache(db)
    if telegram_id in cache:
        return cache[telegram_id]
    stmt = select(User).where(
        User.telegram_id == telegram_id,
        User.deleted_at.is_(None),
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    cache[telegram_id] = user
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Look up a user by primary key, honouring soft-delete.

    Used by handlers that have an internal ``user_id`` (e.g. from an
    Expense row) and need to resolve back to ``User`` for things like
    Telegram ID — replaces ad-hoc ``select(User)`` queries inside
    handlers, which violate the layer contract in CLAUDE.md § 0.1.
    """
    stmt = select(User).where(
        User.id == user_id,
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
    # Seed the request-scoped cache so subsequent lookups in this session
    # (e.g. the worker stamping user_id on telegram_updates) skip the DB.
    _get_or_init_user_cache(db)[telegram_id] = user
    return user, True


async def get_month_total(
    db: AsyncSession, user_id: uuid.UUID, month_key: str | None = None
) -> float:
    month_key = month_key or current_month_key()
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.month_key == month_key,
        Expense.deleted_at.is_(None),
        Expense.transaction_type == "expense",
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
        Expense.transaction_type == "expense",
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
            Expense.transaction_type == "expense",
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
            Expense.transaction_type == "expense",
        )
        .group_by(Expense.expense_date)
    )
    rows = (await db.execute(stmt)).all()
    by_day = {row.day: float(row.total or 0) for row in rows}

    trend = []
    current = start_date
    while current <= end_date:
        trend.append({"date": current.isoformat(), "amount": by_day.get(current, 0.0)})
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
            Expense.transaction_type == "expense",
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
