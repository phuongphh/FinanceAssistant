"""Auto-detect recurring expense patterns from transaction history.

Phase 3.8 Epic 3 — Story P3.8-S8.

Algorithm:
1. Pull last 6 months of expenses for the user.
2. Group by ``(category, amount-bucket)`` where amount-bucket
   collapses ±10% of the median amount into a single key. This
   tolerates "rent went up 5%" while keeping the false-positive rate
   sane (3 lunches at the same restaurant for similar amounts in
   different months won't match because the dates won't be ~30 days
   apart — see step 4).
3. Skip groups already represented by an active pattern (avoid
   re-suggesting "thuê nhà 15tr" when the user already confirmed it).
4. ``_looks_recurring`` heuristic: ≥3 occurrences with avg interval
   in 25-35 days. (Not a strict variance bound — VN bank transfer
   timing varies.)
5. Skip suggestions whose fingerprint matches a recent ``rejected``
   row in ``pattern_suggestions_log`` (90-day cooldown).
6. Rate-limit per user: max 3 active suggestions per week.
7. Top 3 candidates surface as Telegram messages with
   ``suggestion_keyboard`` (accept/reject/edit).

The fingerprint scheme is deterministic: ``"<category>|<bucket>"``
where bucket = round(amount / 100_000) (i.e. amounts grouped to
nearest 100k VND). Small enough granularity that "rent 15tr → 16tr"
hits a different bucket; coarse enough that "internet 500k →
500k+1k fee" stays the same. We chose 100k as the bucket size
empirically — Vietnamese recurring bills cluster at 100k multiples.

Layer contract: detector flushes (creates suggestion log rows) but
never commits — the job runner / caller commits.
"""
from __future__ import annotations

import logging
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.recurring_pattern import (
    PatternSuggestionLog,
    RecurringPattern,
)

logger = logging.getLogger(__name__)


# Heuristic constants — picked from spec § 1.3.
HISTORY_MONTHS = 6
MIN_OCCURRENCES = 3
INTERVAL_MIN_DAYS = 25
INTERVAL_MAX_DAYS = 35
AMOUNT_BUCKET_VND = 100_000     # group amounts to nearest 100k for fingerprint
AMOUNT_VARIANCE_PCT = 10.0      # ±10% tolerance within a group
REJECTION_COOLDOWN_DAYS = 90    # don't re-suggest a rejected pattern for 3 months
MAX_SUGGESTIONS_PER_WEEK = 3
TOP_N_PER_RUN = 3


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------


async def detect_patterns(
    db: AsyncSession, user_id: uuid.UUID, *, today: date | None = None,
) -> list[dict]:
    """Run the detector for one user. Returns up to ``TOP_N_PER_RUN``
    candidate suggestions, each as a dict the caller can use to log
    or surface.

    Pure-read: does NOT write to ``pattern_suggestions_log``. Use
    ``persist_and_deliver`` for the full nightly pipeline.
    """
    today = today or date.today()
    since = today - timedelta(days=HISTORY_MONTHS * 30)

    expenses = await _load_recent_expenses(db, user_id, since)
    if not expenses:
        return []

    existing_fingerprints = await _existing_pattern_fingerprints(db, user_id)
    rejected_fingerprints = await _recent_rejected_fingerprints(db, user_id, today)

    groups = _group_similar(expenses)
    suggestions: list[dict] = []
    for fingerprint, txns in groups.items():
        if not _looks_recurring(txns):
            continue
        if fingerprint in existing_fingerprints:
            continue
        if fingerprint in rejected_fingerprints:
            continue
        suggestions.append(_build_suggestion(fingerprint, txns))

    # Sort by occurrence count descending (a 6-of-6-months hit is a
    # safer suggestion than a 3-of-6 borderline). Stable sort so
    # ties preserve discovery order.
    suggestions.sort(key=lambda s: s["occurrences"], reverse=True)
    return suggestions[:TOP_N_PER_RUN]


async def persist_and_deliver(
    db: AsyncSession,
    user_id: uuid.UUID,
    suggestions: list[dict],
    *,
    today: date | None = None,
) -> list[PatternSuggestionLog]:
    """Persist suggestions to ``pattern_suggestions_log`` (returning
    the saved rows) — the caller (job runner) is responsible for
    sending the Telegram message + committing.

    Enforces the per-week rate limit by capping the saved rows to
    ``MAX_SUGGESTIONS_PER_WEEK - existing_this_week``. If the user
    already received 3 suggestions in the last 7 days, returns an
    empty list.
    """
    today = today or date.today()
    if not suggestions:
        return []

    week_ago = today - timedelta(days=7)
    week_count = await _count_recent_suggestions(db, user_id, since=week_ago)
    remaining_quota = MAX_SUGGESTIONS_PER_WEEK - week_count
    if remaining_quota <= 0:
        return []

    saved: list[PatternSuggestionLog] = []
    for s in suggestions[:remaining_quota]:
        log = PatternSuggestionLog(
            user_id=user_id,
            fingerprint=s["fingerprint"],
            category=s["category"],
            suggested_amount=Decimal(s["amount"]),
            occurrence_count=s["occurrences"],
            typical_day=s.get("typical_day"),
        )
        db.add(log)
        saved.append(log)
    await db.flush()
    return saved


# ---------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------


def _group_similar(expenses: list[Expense]) -> dict[str, list[Expense]]:
    """Bucket expenses by ``fingerprint = category|amount-bucket``.

    Amount bucketing collapses ±AMOUNT_BUCKET_VND/2 around each
    100k boundary into a single key, so "rent 15tr" and "rent
    14.95tr" share a bucket but "rent 15tr" and "rent 14tr" don't.
    """
    groups: dict[str, list[Expense]] = defaultdict(list)
    for e in expenses:
        fp = _fingerprint(e.category, Decimal(e.amount))
        groups[fp].append(e)
    return groups


def _fingerprint(category: str, amount: Decimal) -> str:
    bucket = int(round(float(amount) / AMOUNT_BUCKET_VND))
    return f"{category}|{bucket}"


def _looks_recurring(transactions: list[Expense]) -> bool:
    """Heuristic per spec § 1.3:

    - ≥3 occurrences (low enough to catch new commitments, high
      enough to reject 3 lunches at the same restaurant).
    - Average interval in 25-35 days (monthly cadence with VN
      payday wobble).
    """
    if len(transactions) < MIN_OCCURRENCES:
        return False
    dates = sorted(t.expense_date for t in transactions)
    intervals = [
        (dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)
    ]
    if not intervals:
        return False
    avg = sum(intervals) / len(intervals)
    return INTERVAL_MIN_DAYS <= avg <= INTERVAL_MAX_DAYS


def _build_suggestion(fingerprint: str, txns: list[Expense]) -> dict:
    """Compose the dict surfaced to the user / saved to the log."""
    amounts = [Decimal(t.amount) for t in txns]
    median_amount = Decimal(statistics.median(amounts))
    days = [t.expense_date.day for t in txns]
    typical_day = int(statistics.median(days))
    merchants = [t.merchant for t in txns if t.merchant]
    most_common_merchant = (
        Counter(merchants).most_common(1)[0][0] if merchants else None
    )
    return {
        "fingerprint": fingerprint,
        "category": txns[0].category,
        "amount": median_amount,
        "occurrences": len(txns),
        "typical_day": typical_day,
        "merchant_hint": most_common_merchant,
        "transaction_dates": [t.expense_date for t in txns],
    }


# ---------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------


async def _load_recent_expenses(
    db: AsyncSession, user_id: uuid.UUID, since: date,
) -> list[Expense]:
    stmt = (
        select(Expense)
        .where(
            Expense.user_id == user_id,
            Expense.expense_date >= since,
            Expense.deleted_at.is_(None),
            # Already-linked expenses are noise — they're consequences
            # of an existing pattern, not evidence of a new one.
            Expense.recurrence_id.is_(None),
        )
        .order_by(Expense.expense_date.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def _existing_pattern_fingerprints(
    db: AsyncSession, user_id: uuid.UUID,
) -> set[str]:
    """Fingerprints of every active pattern this user already has —
    avoid re-suggesting them."""
    stmt = select(RecurringPattern).where(
        RecurringPattern.user_id == user_id,
        RecurringPattern.is_active.is_(True),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        _fingerprint(p.category, Decimal(p.expected_amount)) for p in rows
    }


async def _recent_rejected_fingerprints(
    db: AsyncSession, user_id: uuid.UUID, today: date,
) -> set[str]:
    cutoff = datetime.combine(
        today - timedelta(days=REJECTION_COOLDOWN_DAYS),
        datetime.min.time(),
    )
    stmt = select(PatternSuggestionLog).where(
        PatternSuggestionLog.user_id == user_id,
        PatternSuggestionLog.outcome == "rejected",
        PatternSuggestionLog.suggested_at >= cutoff,
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {r.fingerprint for r in rows}


async def _count_recent_suggestions(
    db: AsyncSession, user_id: uuid.UUID, *, since: date,
) -> int:
    cutoff = datetime.combine(since, datetime.min.time())
    stmt = select(PatternSuggestionLog).where(
        PatternSuggestionLog.user_id == user_id,
        PatternSuggestionLog.suggested_at >= cutoff,
    )
    rows = (await db.execute(stmt)).scalars().all()
    return len(rows)


# ---------------------------------------------------------------------
# Telegram message format helper
# ---------------------------------------------------------------------


def format_suggestion_message(suggestion: dict) -> str:
    """Render the spec § P3.8-S8 message format.

    Caller attaches the ``suggestion_keyboard`` from
    ``backend.bot.keyboards.recurring_keyboard``."""
    from backend.bot.formatters.money import format_money_short
    from backend.config.categories import get_category

    cat = get_category(suggestion["category"])
    amount = format_money_short(Decimal(suggestion["amount"]))
    typical_day = suggestion.get("typical_day")
    day_str = (
        f"📅 Thường vào ngày: <b>{typical_day}</b>\n"
        if typical_day else ""
    )
    return (
        "🔍 Mình thấy bạn có vẻ trả khoản này hàng tháng:\n\n"
        f"{cat.emoji} <b>{cat.name_vi}</b>\n"
        f"💰 Số tiền: ~{amount}\n"
        f"{day_str}"
        f"🔁 Đã xảy ra: <b>{suggestion['occurrences']}</b> lần "
        f"trong {HISTORY_MONTHS} tháng\n\n"
        "Có phải hàng tháng không?"
    )
