"""Recurring-pattern CRUD + lifecycle helpers.

Phase 3.8 Epic 3 — see ``backend.models.recurring_pattern`` for the
domain model.

Public surface:

- ``add_pattern`` / ``update_pattern`` / ``disable_pattern``
- ``get_active_patterns`` / ``get_pattern_by_id``
- ``link_transaction_to_pattern`` — point an existing Expense row at
  a pattern + bump pattern.last_occurrence_date.
- ``record_occurrence`` — create a new Expense from a "Đã trả"
  reminder tap.
- ``get_next_expected_date`` — schedule arithmetic, single source of
  truth for both the reminder scheduler and the wizard's "lần sau dự
  kiến" confirmation.
- ``was_paid_this_period`` — guard against double-reminders.
- ``snooze_pattern`` — push the next reminder out by N days.

Layer contract: service flushes only — caller commits.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.recurring_pattern import RecurringPattern


# ---------------------------------------------------------------------
# Mutation API
# ---------------------------------------------------------------------


async def add_pattern(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    category: str,
    expected_amount: Decimal,
    schedule_type: str = "monthly",
    expected_day_of_month: int | None = None,
    enable_reminders: bool = True,
    reminder_days_before: int = 2,
    auto_detected: bool = False,
    user_confirmed: bool = True,
) -> RecurringPattern:
    """Create a new pattern. ``user_confirmed`` defaults True for
    manual entries (the user is right there typing it); the auto-
    detection path passes ``user_confirmed=False`` until the user
    taps "✅ Đúng" on the suggestion.
    """
    if expected_amount is None or Decimal(expected_amount) <= 0:
        raise ValueError("expected_amount must be positive")
    if expected_day_of_month is not None and not (
        1 <= expected_day_of_month <= 31
    ):
        raise ValueError("expected_day_of_month must be 1-31")

    pattern = RecurringPattern(
        user_id=user_id,
        name=name,
        category=category,
        expected_amount=Decimal(expected_amount),
        schedule_type=schedule_type,
        expected_day_of_month=expected_day_of_month,
        enable_reminders=enable_reminders,
        reminder_days_before=reminder_days_before,
        auto_detected=auto_detected,
        user_confirmed=user_confirmed,
        is_active=True,
        occurrence_count=0,
    )
    db.add(pattern)
    await db.flush()
    return pattern


async def update_pattern(
    db: AsyncSession,
    user_id: uuid.UUID,
    pattern_id: uuid.UUID,
    **updates: Any,
) -> RecurringPattern:
    """Apply a partial update — only fields explicitly passed in
    ``updates`` are touched. Mirrors ``income_service.update_income_
    stream`` shape.

    Raises ``ValueError`` when the pattern doesn't exist or belongs
    to another user.
    """
    pattern = await _get_owned(db, user_id, pattern_id)
    if pattern is None:
        raise ValueError(f"Pattern {pattern_id} not found for user {user_id}")
    for field, value in updates.items():
        if not hasattr(pattern, field):
            raise ValueError(f"Unknown field: {field}")
        setattr(pattern, field, value)
    pattern.updated_at = datetime.utcnow()
    await db.flush()
    return pattern


async def disable_pattern(
    db: AsyncSession, user_id: uuid.UUID, pattern_id: uuid.UUID
) -> RecurringPattern:
    """Soft-delete: ``is_active=False``. Reversible via
    ``update_pattern(..., is_active=True)`` if the user changes their
    mind. Distinct from disabling reminders — pause the pattern
    entirely vs just stop pinging."""
    pattern = await _get_owned(db, user_id, pattern_id)
    if pattern is None:
        raise ValueError(f"Pattern {pattern_id} not found")
    pattern.is_active = False
    pattern.updated_at = datetime.utcnow()
    await db.flush()
    return pattern


async def disable_reminders(
    db: AsyncSession, user_id: uuid.UUID, pattern_id: uuid.UUID
) -> RecurringPattern:
    """Set ``enable_reminders=False`` without disabling the pattern
    itself — the user wants to remember this commitment but not be
    pinged about it."""
    pattern = await _get_owned(db, user_id, pattern_id)
    if pattern is None:
        raise ValueError(f"Pattern {pattern_id} not found")
    pattern.enable_reminders = False
    pattern.updated_at = datetime.utcnow()
    await db.flush()
    return pattern


async def snooze_pattern(
    db: AsyncSession,
    user_id: uuid.UUID,
    pattern_id: uuid.UUID,
    *,
    days: int = 2,
) -> RecurringPattern:
    """Push the next reminder out by ``days``. Used by the "trễ vài
    ngày" callback so the scheduler skips this pattern until the
    snooze window expires."""
    if days <= 0:
        raise ValueError("days must be positive")
    pattern = await _get_owned(db, user_id, pattern_id)
    if pattern is None:
        raise ValueError(f"Pattern {pattern_id} not found")
    pattern.snooze_until = date.today() + timedelta(days=days)
    pattern.updated_at = datetime.utcnow()
    await db.flush()
    return pattern


async def link_transaction_to_pattern(
    db: AsyncSession,
    user_id: uuid.UUID,
    transaction_id: uuid.UUID,
    pattern_id: uuid.UUID,
) -> Expense:
    """Point an existing transaction at a pattern + bump tracking.

    Used by the daily reconciliation path (Phase 4) when the user
    pays via a non-bot channel and the matcher finds an unlinked
    expense in the variance window. Manual reminder-paid taps go
    through ``record_occurrence`` instead.
    """
    pattern = await _get_owned(db, user_id, pattern_id)
    if pattern is None:
        raise ValueError(f"Pattern {pattern_id} not found")

    expense = await db.get(Expense, transaction_id)
    if expense is None or expense.user_id != user_id:
        raise ValueError(f"Transaction {transaction_id} not found")

    expense.recurrence_id = pattern_id
    expense.is_recurring = True
    pattern.last_occurrence_date = expense.expense_date
    pattern.occurrence_count = (pattern.occurrence_count or 0) + 1
    pattern.updated_at = datetime.utcnow()
    await db.flush()
    return expense


async def record_occurrence(
    db: AsyncSession,
    user_id: uuid.UUID,
    pattern_id: uuid.UUID,
    *,
    amount: Decimal | None = None,
    expense_date: date | None = None,
    note: str | None = None,
    source: str = "reminder_paid",
) -> Expense:
    """Create a new Expense linked to ``pattern_id`` + bump tracking.

    Defaults make the "Đã trả" reminder tap a one-step action: the
    user confirms and we use ``pattern.expected_amount`` and today's
    date. They can override either via the wizard.
    """
    pattern = await _get_owned(db, user_id, pattern_id)
    if pattern is None:
        raise ValueError(f"Pattern {pattern_id} not found")

    eff_amount = Decimal(amount) if amount is not None else Decimal(pattern.expected_amount)
    if eff_amount <= 0:
        raise ValueError("amount must be positive")
    eff_date = expense_date or date.today()
    month_key = eff_date.strftime("%Y-%m")

    expense = Expense(
        user_id=user_id,
        amount=eff_amount,
        currency="VND",
        merchant=pattern.name,
        category=pattern.category,
        source=source,
        expense_date=eff_date,
        month_key=month_key,
        note=note,
        is_recurring=True,
        recurrence_id=pattern_id,
    )
    db.add(expense)
    pattern.last_occurrence_date = eff_date
    pattern.occurrence_count = (pattern.occurrence_count or 0) + 1
    pattern.updated_at = datetime.utcnow()
    await db.flush()
    return expense


# ---------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------


async def get_active_patterns(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    include_inactive: bool = False,
) -> list[RecurringPattern]:
    """List patterns for a user, default active-only.

    Sorted by ``expected_day_of_month`` so the list view shows
    upcoming-first (a user scanning the list is most often deciding
    whether they need to act *today*).
    """
    stmt = select(RecurringPattern).where(
        RecurringPattern.user_id == user_id,
    )
    if not include_inactive:
        stmt = stmt.where(RecurringPattern.is_active.is_(True))
    stmt = stmt.order_by(
        RecurringPattern.expected_day_of_month.asc().nulls_last(),
        RecurringPattern.created_at.desc(),
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_pattern_by_id(
    db: AsyncSession, user_id: uuid.UUID, pattern_id: uuid.UUID
) -> RecurringPattern | None:
    return await _get_owned(db, user_id, pattern_id)


async def was_paid_this_period(
    db: AsyncSession,
    pattern: RecurringPattern,
    *,
    today: date | None = None,
) -> bool:
    """``True`` if any expense linked to this pattern lands in the
    current billing period.

    Period definition for monthly patterns: the calendar month
    containing the most recent ``expected_day_of_month``. Reminder
    scheduler uses this to skip "you owe" pings when the user
    already paid via storytelling / OCR / manual entry.
    """
    today = today or date.today()
    period_start = _current_period_start(pattern, today)
    period_end = _current_period_end(pattern, today)

    stmt = select(Expense.id).where(
        Expense.recurrence_id == pattern.id,
        Expense.expense_date >= period_start,
        Expense.expense_date <= period_end,
        Expense.deleted_at.is_(None),
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


# ---------------------------------------------------------------------
# Schedule arithmetic
# ---------------------------------------------------------------------


def get_next_expected_date(
    pattern: RecurringPattern, *, today: date | None = None
) -> date:
    """Compute the next due date for a pattern.

    For monthly schedules with ``expected_day_of_month=D``:
    - If today's day ≤ D AND we haven't already had an occurrence
      this month: the date is THIS month's D (clamped if D > end of
      month — Feb 31 → Feb 28/29).
    - Otherwise: NEXT month's D, clamped.

    For monthly schedules without ``expected_day_of_month``: fall
    back to "30 days after last_occurrence_date" — best we can do
    without a fixed day. Detector auto-fills the day for
    auto-detected patterns; the manual wizard makes it required, so
    the unset path is rare.
    """
    today = today or date.today()
    if pattern.schedule_type != "monthly":
        # Non-monthly schedules aren't shipped in Phase 3.8 — fall
        # back to a 30-day default rather than throwing, so a future
        # quarterly pattern doesn't crash existing readers.
        last = pattern.last_occurrence_date or today
        return last + timedelta(days=30)

    day = pattern.expected_day_of_month
    if day is None:
        last = pattern.last_occurrence_date or today
        return last + timedelta(days=30)

    # Has the user already paid for this month? If so jump straight
    # to next month. ``last_occurrence_date`` is the cheap proxy —
    # the reminder scheduler does a stricter check via
    # ``was_paid_this_period``.
    if pattern.last_occurrence_date and (
        pattern.last_occurrence_date.year == today.year
        and pattern.last_occurrence_date.month == today.month
    ):
        return _clamped_day(today.year, today.month + 1, day)

    candidate = _clamped_day(today.year, today.month, day)
    if candidate >= today:
        return candidate
    return _clamped_day(today.year, today.month + 1, day)


def _clamped_day(year: int, month: int, day: int) -> date:
    """Return ``date(year, month, day)`` clamped to month length.

    Handles year wrap (month=13 → next January) and month-end
    clamping (Feb 31 → Feb 28/29). The scheduler relies on this
    being total — we never want a reminder to silently disappear
    because Feb has no day 30.
    """
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    last_dom = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_dom))


def _current_period_start(pattern: RecurringPattern, today: date) -> date:
    """First day of the period that contains ``today``.

    For monthly: the 1st of the current calendar month (independent
    of ``expected_day_of_month``). Simplifies "was paid this period"
    to "any expense in this calendar month for this pattern".
    """
    return date(today.year, today.month, 1)


def _current_period_end(pattern: RecurringPattern, today: date) -> date:
    """Last day of the period that contains ``today``."""
    last_dom = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, last_dom)


# ---------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------


async def _get_owned(
    db: AsyncSession, user_id: uuid.UUID, pattern_id: uuid.UUID
) -> RecurringPattern | None:
    stmt = select(RecurringPattern).where(
        and_(
            RecurringPattern.id == pattern_id,
            RecurringPattern.user_id == user_id,
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()
