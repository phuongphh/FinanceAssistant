"""Phase 4B S14 — Cashflow recurring pattern detector.

Algorithm (rule-based, no ML):

1. Pull last ``lookback_months`` of transactions for the user
   (expenses + income records).
2. Group by (category_id|income_type, amount_band_50k, day_band_3days):
   - amount_band_50k: round(amount / 50000) * 50000
   - day_band: bucket day-of-month into 8 bands ([1-4],[5-7],...,[28-31])
3. For each group spanning ≥ min_occurrences distinct months and
   confidence ≥ confidence_threshold, emit a RecurringCandidate.
4. Skip groups whose fingerprint already has an active pattern OR was
   dismissed within 30 days.
5. Persist candidates as *unconfirmed* RecurringPattern rows (or update
   existing ones). The user then confirms/dismisses via the Telegram
   review flow (S15).

Performance: < 2s for 500 transactions on a single-core VPS.

Layer contract: detector flushes — caller (cron job) commits.
"""
from __future__ import annotations

import logging
import statistics
import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.recurring_pattern import (
    PATTERN_TYPE_EXPENSE,
    PATTERN_TYPE_INCOME,
    RecurringPattern,
)
from backend.wealth.models.income_stream import IncomeStream

logger = logging.getLogger(__name__)

# ── Tuning constants ────────────────────────────────────────────────────────

LOOKBACK_MONTHS = 3
MIN_OCCURRENCES = 3            # ≥ 3 distinct months
CONFIDENCE_THRESHOLD = 0.70    # confidence = distinct_months / lookback
AMOUNT_BAND_VND = 50_000       # group amounts to nearest 50k
DISMISS_COOLDOWN_DAYS = 30     # don't re-prompt dismissed patterns

# Day-of-month bands (8 buckets, roughly 4-day windows).
# Using fixed bands rather than standard deviation so the buckets are
# stable across months and portable across calendar years.
_DAY_BANDS: list[tuple[int, int]] = [
    (1, 4), (5, 7), (8, 11), (12, 15),
    (16, 19), (20, 23), (24, 27), (28, 31),
]


# ── Data structures ─────────────────────────────────────────────────────────


class RecurringCandidate(NamedTuple):
    fingerprint: str
    pattern_type: str          # PATTERN_TYPE_INCOME | PATTERN_TYPE_EXPENSE
    category_key: str          # category or income_type string
    amount: Decimal            # median amount (positive)
    typical_day: int           # modal day of month
    frequency: str             # 'monthly' (only option for now)
    confidence: Decimal        # 0.00–1.00
    description: str           # human-readable label for Telegram/UI


# ── Public API ───────────────────────────────────────────────────────────────


async def detect_and_upsert(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    lookback_months: int = LOOKBACK_MONTHS,
    min_occurrences: int = MIN_OCCURRENCES,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    today: date | None = None,
) -> list[RecurringPattern]:
    """Detect recurring patterns and upsert them into recurring_patterns.

    Returns the list of newly-created or updated *unconfirmed* pattern rows
    so the caller (review job) can send Telegram review messages for them.
    Only rows that are new or changed (confidence updated) are returned —
    already-confirmed rows are silently skipped.

    Pure write (flush only). Caller commits.
    """
    today = today or date.today()
    since = _month_start(today, -lookback_months)

    expenses = await _load_expenses(db, user_id, since)
    income_records = await _load_income_records(db, user_id, since)
    income_streams = await _load_income_streams(db, user_id)

    candidates = _detect_candidates(
        expenses, income_records, income_streams,
        lookback_months=lookback_months,
        min_occurrences=min_occurrences,
        confidence_threshold=confidence_threshold,
    )

    now = datetime.utcnow()
    upserted: list[RecurringPattern] = []

    for candidate in candidates:
        existing = await _find_existing_pattern(db, user_id, candidate.fingerprint)

        if existing is not None:
            # Already confirmed → don't touch it; the user owns it now.
            if existing.user_confirmed:
                continue
            # Dismissed within cooldown → skip.
            if _is_dismissed(existing, now):
                continue
            # Update confidence + last_seen only.
            existing.confidence = candidate.confidence
            existing.last_seen_at = now
            db.add(existing)
            upserted.append(existing)
        else:
            pattern = RecurringPattern(
                user_id=user_id,
                name=candidate.description,
                description=candidate.description,
                category=candidate.category_key,
                expected_amount=candidate.amount,
                schedule_type=candidate.frequency,
                expected_day_of_month=candidate.typical_day,
                pattern_type=candidate.pattern_type,
                confidence=candidate.confidence,
                is_active=True,
                auto_detected=True,
                user_confirmed=False,
                enable_reminders=False,   # reminders off until user confirms
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(pattern)
            upserted.append(pattern)

    await db.flush()
    logger.info(
        "cashflow detector: user=%s lookback=%dm candidates=%d upserted=%d",
        user_id, lookback_months, len(candidates), len(upserted),
    )
    return upserted


async def load_confirmed_patterns(
    db: AsyncSession, user_id: uuid.UUID,
) -> list[RecurringPattern]:
    """Return confirmed patterns used by the forecast engine."""
    stmt = select(RecurringPattern).where(
        and_(
            RecurringPattern.user_id == user_id,
            RecurringPattern.user_confirmed.is_(True),
            RecurringPattern.is_active.is_(True),
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def load_unconfirmed_pending(
    db: AsyncSession, user_id: uuid.UUID,
    *,
    now: datetime | None = None,
    limit: int = 5,
) -> list[RecurringPattern]:
    """Return auto-detected patterns awaiting user review.

    Excludes confirmed patterns and those currently dismissed.
    Capped at ``limit`` to avoid overwhelming users (spec S15).
    """
    now = now or datetime.utcnow()
    stmt = (
        select(RecurringPattern)
        .where(
            and_(
                RecurringPattern.user_id == user_id,
                RecurringPattern.user_confirmed.is_(False),
                RecurringPattern.auto_detected.is_(True),
                RecurringPattern.is_active.is_(True),
            )
        )
        .order_by(RecurringPattern.confidence.desc())
        .limit(limit * 2)   # fetch extra to filter dismissed in Python
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return [r for r in rows if not _is_dismissed(r, now)][:limit]


# ── Detection internals ──────────────────────────────────────────────────────


def _detect_candidates(
    expenses: list[Expense],
    income_records: list,
    income_streams: list[IncomeStream],
    *,
    lookback_months: int,
    min_occurrences: int,
    confidence_threshold: float,
) -> list[RecurringCandidate]:
    groups: dict[str, list[tuple[date, Decimal, str]]] = defaultdict(list)

    # Expense groups
    for e in expenses:
        key = _fingerprint(
            PATTERN_TYPE_EXPENSE, e.category, Decimal(str(e.amount))
        )
        groups[key].append((e.expense_date, Decimal(str(e.amount)), e.category))

    # Income record groups (manual income log entries)
    for ir in income_records:
        key = _fingerprint(
            PATTERN_TYPE_INCOME,
            getattr(ir, "income_type", "income"),
            Decimal(str(ir.amount)),
        )
        groups[key].append((
            getattr(ir, "period", ir.created_at.date() if hasattr(ir, "created_at") else date.today()),
            Decimal(str(ir.amount)),
            getattr(ir, "income_type", "income"),
        ))

    candidates: list[RecurringCandidate] = []
    for fingerprint, items in groups.items():
        dates = [d for d, _, _ in items]
        amounts = [a for _, a, _ in items]
        category = items[0][2]

        unique_months = {(d.year, d.month) for d in dates}
        if len(unique_months) < min_occurrences:
            continue

        confidence = Decimal(str(round(len(unique_months) / lookback_months, 4)))
        if float(confidence) < confidence_threshold:
            continue

        pattern_type = (
            PATTERN_TYPE_INCOME
            if fingerprint.startswith(PATTERN_TYPE_INCOME + "|")
            else PATTERN_TYPE_EXPENSE
        )
        median_amount = Decimal(str(statistics.median(float(a) for a in amounts)))
        typical_day = _modal_day(dates)
        description = _build_description(pattern_type, category, median_amount)

        candidates.append(RecurringCandidate(
            fingerprint=fingerprint,
            pattern_type=pattern_type,
            category_key=category,
            amount=median_amount,
            typical_day=typical_day,
            frequency="monthly",
            confidence=confidence,
            description=description,
        ))

    # Sort by confidence desc so high-confidence patterns are reviewed first.
    candidates.sort(key=lambda c: float(c.confidence), reverse=True)
    return candidates


def _fingerprint(pattern_type: str, category: str, amount: Decimal) -> str:
    band = int(round(float(amount) / AMOUNT_BAND_VND))
    return f"{pattern_type}|{category}|{band}"


def _day_band(day: int) -> int:
    """Map day-of-month (1-31) to the lower bound of its 4-day bucket."""
    for lo, hi in _DAY_BANDS:
        if lo <= day <= hi:
            return lo
    return 28  # safety fallback for day=29/30/31


def _modal_day(dates: list[date]) -> int:
    """Most common day-of-month across the occurrence dates."""
    if not dates:
        return 1
    days = [d.day for d in dates]
    return max(set(days), key=days.count)


def _build_description(pattern_type: str, category: str, amount: Decimal) -> str:
    from backend.bot.formatters.money import format_money_short
    amt_str = format_money_short(amount)
    if pattern_type == PATTERN_TYPE_INCOME:
        return f"Thu nhập định kỳ: {category} ~{amt_str}"
    return f"Chi định kỳ: {category} ~{amt_str}"


# ── DB helpers ───────────────────────────────────────────────────────────────


async def _find_existing_pattern(
    db: AsyncSession, user_id: uuid.UUID, fingerprint: str,
) -> RecurringPattern | None:
    stmt = select(RecurringPattern).where(
        and_(
            RecurringPattern.user_id == user_id,
            RecurringPattern.name == fingerprint,  # stored in name for dedup
            RecurringPattern.is_active.is_(True),
        )
    )
    result = (await db.execute(stmt)).scalars().first()
    return result


def _is_dismissed(pattern: RecurringPattern, now: datetime) -> bool:
    if pattern.dismissed_until is None:
        return False
    dismissed_dt = pattern.dismissed_until
    if dismissed_dt.tzinfo is None:
        dismissed_dt = dismissed_dt.replace(tzinfo=None)
        return now < dismissed_dt
    return now.replace(tzinfo=None) < dismissed_dt.replace(tzinfo=None)


async def _load_expenses(
    db: AsyncSession, user_id: uuid.UUID, since: date,
) -> list[Expense]:
    stmt = (
        select(Expense)
        .where(
            and_(
                Expense.user_id == user_id,
                Expense.expense_date >= since,
                Expense.deleted_at.is_(None),
            )
        )
        .order_by(Expense.expense_date.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def _load_income_records(
    db: AsyncSession, user_id: uuid.UUID, since: date,
) -> list:
    """Load income records if the model exists; return empty list otherwise."""
    try:
        from backend.models.income_record import IncomeRecord
        stmt = (
            select(IncomeRecord)
            .where(
                and_(
                    IncomeRecord.user_id == user_id,
                    IncomeRecord.period >= since,
                )
            )
        )
        return list((await db.execute(stmt)).scalars().all())
    except Exception:
        return []


async def _load_income_streams(
    db: AsyncSession, user_id: uuid.UUID,
) -> list[IncomeStream]:
    stmt = select(IncomeStream).where(
        and_(
            IncomeStream.user_id == user_id,
            IncomeStream.is_active.is_(True),
        )
    )
    return list((await db.execute(stmt)).scalars().all())


def _month_start(today: date, offset_months: int) -> date:
    """First day of the month ``offset_months`` from ``today``."""
    month = today.month + offset_months
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return date(year, month, 1)
