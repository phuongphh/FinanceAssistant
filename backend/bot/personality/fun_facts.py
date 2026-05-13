"""Weekly fun-fact generator — Phase 2, Issue #42.

Computes a menu of possible facts from the user's last 30 days (some
checks use 7 days). Returns the first eligible fact in a fixed priority
order; if none qualify, falls back to the always-applicable biggest-
category fact.

Why a fixed priority instead of "random among eligible"?
  Random makes the feature feel slot-machiney. A user who bought coffee
  a lot would rather see the coffee fact (which makes them laugh) than
  a generic top-category restatement — so the specific facts outrank
  the generic one. This reads like curation, not roulette.

Efficiency note: all aggregations derive from **one** Expense SELECT
per user per run. Individual ``_compute_*`` helpers take an already-
materialised list of rows so we don't round-trip to Postgres six times
per user.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full
from backend.config.categories import get_category
from backend.models.expense import Expense
from backend.models.user import User
from backend.utils.categories import normalize_category

logger = logging.getLogger(__name__)

_TEMPLATES_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "content"
    / "fun_fact_templates.yaml"
)
_templates_cache: dict | None = None


def _load_templates() -> dict:
    global _templates_cache
    if _templates_cache is None:
        with open(_TEMPLATES_PATH, encoding="utf-8") as f:
            _templates_cache = yaml.safe_load(f) or {}
    return _templates_cache


def reload_templates_for_tests() -> None:
    global _templates_cache
    _templates_cache = None


# Merchant-name regex patterns used to classify specific brands. Keep
# them loose so variations ("Grab", "Grab Vietnam", "GRABPAY") all hit.
_COFFEE_RE = re.compile(
    r"(?i)\b(highlands|starbucks|phuc long|phúc long|the coffee house|tch|"
    r"cafe|café|coffee|trung nguyên|trung nguyen|katinat|cheese coffee)\b"
)
_GRAB_RE = re.compile(r"(?i)\bgrab(?!food)", re.IGNORECASE)
_FOOD_DELIVERY_RE = re.compile(
    r"(?i)\b(grabfood|grab food|shopeefood|shopee food|befood|be food|baemin|loship|now)\b"
)

# Average VND per Highlands Vietnamese coffee (2025/26 street price).
# Used for the "bằng N ly" joke only — if a user has a different daily
# driver (Trung Nguyên, Phúc Long), it's a close-enough approximation.
AVG_HIGHLANDS_CUP_VND = 55_000


# ---------- Shared row type + bulk fetch ---------------------------

@dataclass(frozen=True)
class _ExpenseRow:
    """Subset of Expense columns the generator needs. Passing tuples or
    MagicMocks through helpers was ambiguous — a typed struct keeps the
    aggregation helpers readable and easy to test."""
    amount: float
    merchant: str | None
    note: str | None
    category: str
    expense_date: date


async def _fetch_expenses(
    db: AsyncSession, user_id: uuid.UUID, *, since: date
) -> list[_ExpenseRow]:
    """Single query — pulls every column all downstream helpers need."""
    stmt = select(
        Expense.amount, Expense.merchant, Expense.note,
        Expense.category, Expense.expense_date,
    ).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= since,
    )
    rows = (await db.execute(stmt)).all()
    return [
        _ExpenseRow(
            amount=float(r[0]),
            merchant=r[1],
            note=r[2],
            category=r[3],
            expense_date=r[4],
        )
        for r in rows
    ]


# ---------- Aggregations (pure, over the materialised list) --------

def _coffee_spend(rows: list[_ExpenseRow]) -> float:
    return sum(r.amount for r in rows if r.merchant and _COFFEE_RE.search(r.merchant))


def _grab_stats(rows: list[_ExpenseRow]) -> tuple[int, float]:
    count = 0
    total = 0.0
    for r in rows:
        text = " ".join(filter(None, [r.merchant, r.note]))
        if not text:
            continue
        # GrabFood / BeFood look like "grab" but are food delivery.
        if _FOOD_DELIVERY_RE.search(text):
            continue
        if _GRAB_RE.search(text):
            count += 1
            total += r.amount
    return count, total


def _food_delivery_stats(rows: list[_ExpenseRow]) -> tuple[int, float]:
    count = 0
    total = 0.0
    for r in rows:
        text = " ".join(filter(None, [r.merchant, r.note]))
        if text and _FOOD_DELIVERY_RE.search(text):
            count += 1
            total += r.amount
    return count, total


def _weekend_weekday_avg(rows: list[_ExpenseRow]) -> tuple[float, float]:
    """Averages by *day*, not event — a user who makes 3 purchases on a
    Saturday should count as one expensive day, not three."""
    by_day: dict[date, float] = {}
    for r in rows:
        by_day[r.expense_date] = by_day.get(r.expense_date, 0.0) + r.amount
    if not by_day:
        return 0.0, 0.0
    weekend_totals = [v for d, v in by_day.items() if d.weekday() >= 5]
    weekday_totals = [v for d, v in by_day.items() if d.weekday() < 5]
    we_avg = sum(weekend_totals) / len(weekend_totals) if weekend_totals else 0.0
    wd_avg = sum(weekday_totals) / len(weekday_totals) if weekday_totals else 0.0
    return we_avg, wd_avg


def _biggest_category(
    rows: list[_ExpenseRow], *, since: date
) -> tuple[str, float, float] | None:
    """Return (normalized_category_code, total_vnd, pct_of_total)."""
    totals: dict[str, float] = {}
    for r in rows:
        if r.expense_date < since:
            continue
        key = normalize_category(r.category)
        totals[key] = totals.get(key, 0.0) + r.amount
    if not totals:
        return None
    grand = sum(totals.values())
    if grand <= 0:
        return None
    top_code, top_total = max(totals.items(), key=lambda kv: kv[1])
    return top_code, top_total, (top_total / grand) * 100.0


def _new_merchant_in_window(
    rows_30d: list[_ExpenseRow], *, window_start: date
) -> str | None:
    """A merchant seen for the first time in the last 7 days.

    Uses the 30-day row set as a proxy for "ever" — good enough for the
    "new place" joke. A truly new merchant won't appear in the older
    portion of the window.
    """
    first_seen: dict[str, date] = {}
    for r in rows_30d:
        if not r.merchant:
            continue
        name = r.merchant.strip()
        if len(name) <= 2:
            continue
        prior = first_seen.get(name)
        if prior is None or r.expense_date < prior:
            first_seen[name] = r.expense_date

    candidates = [
        (name, first) for name, first in first_seen.items()
        if first >= window_start
    ]
    if not candidates:
        return None
    # Most recently first-seen → freshest joke.
    candidates.sort(key=lambda kv: kv[1])
    return candidates[-1][0]


# ---------- Fact generation -----------------------------------------

@dataclass(frozen=True)
class FunFact:
    """Rendered fact ready to send."""
    key: str     # template key, useful for analytics/dedup
    text: str    # final message


def _name_of(user: User) -> str:
    return user.get_greeting_name()


def _render_coffee(user: User, spend: float) -> FunFact:
    template = _load_templates()["coffee_equivalent"]["template"]
    cups = max(1, int(round(spend / AVG_HIGHLANDS_CUP_VND)))
    saving = spend * 0.7  # Rough "what if you brewed at home" heuristic.
    text = template.format(
        name=_name_of(user),
        amount=format_money_full(spend),
        coffee_count=cups,
        saving=format_money_full(saving),
    )
    return FunFact(key="coffee_equivalent", text=text)


def _render_grab(user: User, count: int, total: float) -> FunFact:
    template = _load_templates()["grab_count"]["template"]
    avg = total / count if count else 0
    text = template.format(
        name=_name_of(user),
        count=count,
        amount=format_money_full(total),
        avg=format_money_full(avg),
    )
    return FunFact(key="grab_count", text=text)


def _render_delivery(user: User, count: int, total: float) -> FunFact:
    template = _load_templates()["food_delivery_count"]["template"]
    saving = total * 0.3
    text = template.format(
        name=_name_of(user),
        count=count,
        amount=format_money_full(total),
        saving=format_money_full(saving),
    )
    return FunFact(key="food_delivery_count", text=text)


def _render_weekend(
    user: User, weekend_avg: float, weekday_avg: float
) -> FunFact:
    template = _load_templates()["weekend_vs_weekday"]["template"]
    ratio = weekend_avg / weekday_avg if weekday_avg else 0
    text = template.format(
        name=_name_of(user),
        weekend_avg=format_money_full(weekend_avg),
        weekday_avg=format_money_full(weekday_avg),
        ratio=f"{ratio:.1f}",
    )
    return FunFact(key="weekend_vs_weekday", text=text)


def _render_biggest_category(
    user: User, category_code: str, amount: float, pct: float
) -> FunFact:
    template = _load_templates()["biggest_category"]["template"]
    cat = get_category(normalize_category(category_code))
    insights = _load_templates().get("category_insights") or {}
    insight_template = insights.get(cat.code) or insights.get("other", "")
    # Insights may themselves contain {name}.
    try:
        insight = insight_template.format(name=_name_of(user))
    except KeyError:
        insight = insight_template
    text = template.format(
        name=_name_of(user),
        category=cat.name_vi,
        amount=format_money_full(amount),
        percentage=f"{int(round(pct))}",
        category_insight=insight,
    )
    return FunFact(key="biggest_category", text=text)


def _render_new_merchant(user: User, merchant: str) -> FunFact:
    template = _load_templates()["new_merchant"]["template"]
    text = template.format(name=_name_of(user), merchant=merchant)
    return FunFact(key="new_merchant", text=text)


# ---------- Entry point --------------------------------------------

async def generate_for_user(
    db: AsyncSession, user: User, *, today: date | None = None
) -> Optional[FunFact]:
    """Pick the most interesting fact applicable to this user.

    Priority (highest first):
      coffee_equivalent → food_delivery_count → grab_count →
      weekend_vs_weekday → new_merchant → biggest_category (fallback)

    Returns ``None`` if the user has literally no data — callers
    interpret that as "skip this user this week".
    """
    today = today or date.today()
    since_30d = today - timedelta(days=30)
    since_7d = today - timedelta(days=6)

    rows_30d = await _fetch_expenses(db, user.id, since=since_30d)

    recent_14d_cutoff = today - timedelta(days=14)
    rows_14d = [r for r in rows_30d if r.expense_date >= recent_14d_cutoff]
    if not rows_14d:
        return None

    coffee = _coffee_spend(rows_30d)
    if coffee > 500_000:
        return _render_coffee(user, coffee)

    del_count, del_total = _food_delivery_stats(rows_30d)
    if del_count >= 10:
        return _render_delivery(user, del_count, del_total)

    grab_count, grab_total = _grab_stats(rows_30d)
    if grab_count >= 5:
        return _render_grab(user, grab_count, grab_total)

    we_avg, wd_avg = _weekend_weekday_avg(rows_30d)
    if wd_avg > 0 and (we_avg / wd_avg) > 1.5:
        return _render_weekend(user, we_avg, wd_avg)

    merchant = _new_merchant_in_window(rows_30d, window_start=since_7d)
    if merchant:
        return _render_new_merchant(user, merchant)

    top = _biggest_category(rows_30d, since=since_7d)
    if top is None:
        return None
    cat_code, total, pct = top
    return _render_biggest_category(user, cat_code, total, pct)
