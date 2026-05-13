"""Empathy engine — Phase 2, Issue #40.

Detects emotionally-meaningful patterns in a user's recent behaviour
and returns a warm, non-judgmental message. Run by the hourly scheduler
(``backend/jobs/check_empathy_triggers.py``).

Design choices
--------------
- **Priority-ordered**: the engine picks the FIRST matching trigger not
  on cooldown. A big splurge is more acute than "silent 7 days" — we
  fire the acute one and skip ambient ones that turn.
- **Cooldown via the events table**: we store
  ``event_type="empathy_fired"`` in the shared ``events`` table (see
  Phase 2 migration note). The trigger name goes in ``properties.trigger``
  so we don't need a new column or table.
- **Content in YAML**: one edit in ``content/empathy_messages.yaml``
  re-tunes copy without a code deploy. Same rationale as milestone
  messages.
- **At-least-MVP**: 4 triggers fully implemented (``large_transaction``,
  ``user_silent_7_days``, ``user_silent_30_days``,
  ``weekend_high_spending``). The remaining 4 are stubs that return
  ``None`` — they need income tracking / budgets which land in later
  issues. YAML carries copy for all 8 so wiring them later is copy-paste.
- **Stateless service**: all queries go through the caller's
  ``AsyncSession``. The engine never commits.
"""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import EventType
from backend.bot.formatters.money import format_money_full
from backend.models.event import Event
from backend.models.expense import Expense
from backend.models.user import User

logger = logging.getLogger(__name__)

_MESSAGES_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "content"
    / "empathy_messages.yaml"
)

_messages_cache: dict[str, dict] | None = None


def _load_messages() -> dict[str, dict]:
    global _messages_cache
    if _messages_cache is None:
        with open(_MESSAGES_PATH, encoding="utf-8") as f:
            _messages_cache = yaml.safe_load(f) or {}
    return _messages_cache


def reload_messages_for_tests() -> None:
    global _messages_cache
    _messages_cache = None


# Minimum amount (VND) a "large transaction" must exceed regardless of
# the 3× median. Stops a user whose baseline is tiny from getting a
# "big!" message for every normal transaction.
LARGE_TX_MIN_ABSOLUTE = 500_000

# Minimum non-deleted expenses in the 30-day window before large-tx
# median is meaningful. Below this, the outlier detection is noise.
LARGE_TX_MIN_SAMPLES = 5

# Categories considered internal transfers — excluded from large-tx.
_INTERNAL_CATEGORIES = frozenset({"transfer", "saving", "savings", "investment"})


@dataclass(frozen=True)
class EmpathyTrigger:
    """Struct returned by a trigger check. Consumed by the engine orchestrator."""
    name: str
    priority: int          # lower = higher priority
    cooldown_days: int
    context: dict


async def check_all_triggers(
    db: AsyncSession, user: User, *, now: datetime | None = None
) -> Optional[EmpathyTrigger]:
    """Walk checks in priority order. Return first trigger not on cooldown.

    ``now`` override is for tests; production callers pass ``None``.
    """
    now = now or datetime.now(timezone.utc)

    # Priority matters: acute signals (big spend) beat ambient ones
    # (silent N days) when both match on the same pass.
    checks = (
        _check_large_transaction,
        _check_payday_splurge,
        _check_over_budget_monthly,
        _check_user_silent_7_days,
        _check_user_silent_30_days,
        _check_weekend_high_spending,
        _check_first_saving_month,
        _check_consecutive_over_budget,
    )

    for check_fn in checks:
        trigger = await check_fn(db, user, now)
        if trigger and not await _is_on_cooldown(
            db, user.id, trigger.name, trigger.cooldown_days, now=now
        ):
            return trigger
    return None


# ---------- Individual triggers -------------------------------------

async def _check_large_transaction(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """Latest expense is > 3× median of last 30 days (transfer-excluded).

    Skips when:
    - Sample size below ``LARGE_TX_MIN_SAMPLES`` — median is unreliable.
    - The expense amount is below ``LARGE_TX_MIN_ABSOLUTE`` — a user
      whose baseline is tiny shouldn't get a "big!" message for 30k.
    - The expense is in an internal-transfer category.
    """
    since = now - timedelta(days=30)

    amounts_stmt = (
        select(Expense.amount, Expense.category, Expense.created_at)
        .where(
            Expense.user_id == user.id,
            Expense.deleted_at.is_(None),
            Expense.created_at >= since,
            Expense.category.notin_(_INTERNAL_CATEGORIES),
        )
        .order_by(Expense.created_at.desc())
    )
    rows = (await db.execute(amounts_stmt)).all()
    if len(rows) < LARGE_TX_MIN_SAMPLES:
        return None

    latest = rows[0]
    latest_amount = float(latest.amount)
    if latest_amount < LARGE_TX_MIN_ABSOLUTE:
        return None

    # Median across the full window (including latest — it's only one
    # sample and dropping it biases the baseline upward for a user with
    # genuinely bimodal spending).
    amounts = sorted(float(r.amount) for r in rows)
    mid = len(amounts) // 2
    if len(amounts) % 2:
        median = amounts[mid]
    else:
        median = (amounts[mid - 1] + amounts[mid]) / 2.0
    if median <= 0 or latest_amount < 3 * median:
        return None

    return EmpathyTrigger(
        name="large_transaction",
        priority=1,
        cooldown_days=1,
        context={"amount": format_money_full(latest_amount)},
    )


async def _check_payday_splurge(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """STUB — needs payday date tracking (not yet modeled)."""
    return None


async def _check_over_budget_monthly(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """STUB — needs per-user budget config (not yet modeled)."""
    return None


async def _check_user_silent_7_days(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """7–29 days since last expense created or bot interaction event.

    The 30-day threshold is handled by a separate check with a longer
    cooldown — we don't want a user who's been gone 35 days to get the
    "7-day" message simply because it fires first in the priority order.
    """
    days_silent = await _days_since_last_activity(db, user.id, now=now)
    if days_silent is None:
        return None
    if 7 <= days_silent < 30:
        return EmpathyTrigger(
            name="user_silent_7_days",
            priority=4,
            cooldown_days=14,
            context={"days_silent": days_silent},
        )
    return None


async def _check_user_silent_30_days(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    days_silent = await _days_since_last_activity(db, user.id, now=now)
    if days_silent is None:
        return None
    if days_silent >= 30:
        return EmpathyTrigger(
            name="user_silent_30_days",
            priority=5,
            cooldown_days=60,
            context={"days_silent": days_silent},
        )
    return None


async def _check_weekend_high_spending(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """Weekend (Sat + Sun) spend > 50% of the trailing 7-day total.

    Window: the most recent completed 7-day period ending *yesterday*,
    so partial days never skew the ratio. Fires once per 30 days.
    """
    yesterday = now.date() - timedelta(days=1)
    start = yesterday - timedelta(days=6)

    stmt = select(Expense.amount, Expense.expense_date).where(
        Expense.user_id == user.id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= start,
        Expense.expense_date <= yesterday,
        Expense.category.notin_(_INTERNAL_CATEGORIES),
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return None

    total = 0.0
    weekend = 0.0
    for amount, dt in rows:
        amt = float(amount)
        total += amt
        # Monday=0 … Saturday=5, Sunday=6
        if dt.weekday() >= 5:
            weekend += amt

    if total <= 0:
        return None
    pct = weekend / total
    if pct <= 0.5:
        return None

    return EmpathyTrigger(
        name="weekend_high_spending",
        priority=6,
        cooldown_days=30,
        context={"weekend_pct": f"{int(round(pct * 100))}%"},
    )


async def _check_first_saving_month(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """STUB — needs income source-of-truth reconciliation."""
    return None


async def _check_consecutive_over_budget(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """STUB — needs per-category budget ceilings."""
    return None


# ---------- Helpers -------------------------------------------------

async def _days_since_last_activity(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime
) -> int | None:
    """Days since the most recent user activity we can observe.

    Two signals, whichever is more recent wins:
    - last non-deleted expense ``created_at``
    - last row in the ``events`` table for this user

    Returns None if we've never seen activity — brand-new users
    shouldn't get "long time no see" messages.
    """
    last_expense_stmt = (
        select(func.max(Expense.created_at))
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
        )
    )
    last_expense_at = (await db.execute(last_expense_stmt)).scalar_one_or_none()

    last_event_stmt = (
        select(func.max(Event.timestamp))
        .where(
            Event.user_id == user_id,
            # Don't count our own wake-up messages as "activity" — that
            # would reset the silence counter forever.
            Event.event_type != EventType.EMPATHY_FIRED,
        )
    )
    last_event_at = (await db.execute(last_event_stmt)).scalar_one_or_none()

    candidates = [ts for ts in (last_expense_at, last_event_at) if ts is not None]
    if not candidates:
        return None
    last = max(candidates)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    delta = now - last
    return max(0, delta.days)


async def _is_on_cooldown(
    db: AsyncSession,
    user_id: uuid.UUID,
    trigger_name: str,
    cooldown_days: int,
    *,
    now: datetime,
) -> bool:
    """True if we fired ``trigger_name`` for this user within the cooldown.

    ``cooldown_days == 0`` means "only ever once" — any prior fire locks
    it out forever.
    """
    stmt = select(func.max(Event.timestamp)).where(
        Event.user_id == user_id,
        Event.event_type == EventType.EMPATHY_FIRED,
        Event.properties["trigger"].astext == trigger_name,
    )
    last_fired = (await db.execute(stmt)).scalar_one_or_none()
    if last_fired is None:
        return False
    if cooldown_days == 0:
        return True  # once-only trigger has already fired
    if last_fired.tzinfo is None:
        last_fired = last_fired.replace(tzinfo=timezone.utc)
    return last_fired > (now - timedelta(days=cooldown_days))


async def count_empathy_fired_today(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None
) -> int:
    """How many empathy messages have fired for this user today (UTC)."""
    now = now or datetime.now(timezone.utc)
    start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
    stmt = select(func.count()).where(
        Event.user_id == user_id,
        Event.event_type == EventType.EMPATHY_FIRED,
        Event.timestamp >= start,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


# ---------- Rendering ----------------------------------------------

def render_message(trigger: EmpathyTrigger, user: User) -> str:
    """Pick a random variation from YAML and substitute placeholders."""
    spec = _load_messages().get(trigger.name) or {}
    templates = spec.get("messages") or []
    if not templates:
        logger.warning("No empathy template for trigger %s", trigger.name)
        return ""

    template = random.choice(templates)
    context = {
        "name": user.get_greeting_name(),
        **trigger.context,
    }
    try:
        return template.format(**context)
    except KeyError as exc:
        logger.warning(
            "Empathy %s missing placeholder %s — returning unrendered",
            trigger.name, exc,
        )
        return template


# ---------- Record-fired ------------------------------------------

async def record_fired(
    db: AsyncSession,
    user_id: uuid.UUID,
    trigger_name: str,
    *,
    now: datetime | None = None,
) -> None:
    """Stamp the shared ``events`` table so cooldown sees this fire.

    TRANSACTION_OWNED_BY_CALLER — the hourly job commits after each user.
    """
    now = now or datetime.now(timezone.utc)
    db.add(
        Event(
            user_id=user_id,
            event_type=EventType.EMPATHY_FIRED,
            properties={"trigger": trigger_name},
            timestamp=now,
        )
    )
    await db.flush()
