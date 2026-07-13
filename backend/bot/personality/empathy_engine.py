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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import EventType
from backend.bot.formatters.money import format_money_full
from backend.bot.formatters.tone import render_tone_variant
from backend.models.event import Event
from backend.models.expense import Expense
from backend.models.twin_view_event import TwinViewEvent
from backend.models.user import User
from backend.services.decision import drift_service
from backend.services.onboarding.onboarding_service import salutation_of

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

# Phase 4.4 Epic 3 — proactive activation nudge window. A user who
# finished onboarding (and thus saw their Twin once) but never came back
# to look again is the classic "saw the WOW, then drifted" case. We nudge
# gently inside this window; past the upper bound the generic
# silent-N-days triggers take over, so this stays a focused
# re-engagement nudge rather than a perpetual one.
ONBOARDING_SILENCE_MIN_DAYS = 3
ONBOARDING_SILENCE_MAX_DAYS = 30

# Distinct days a user must have viewed the Twin on before we consider
# them "returned". Onboarding does NOT write a TwinViewEvent (the first
# Twin shown at the end of onboarding is tracked separately via
# ``mark_twin_shown``), so the baseline count is 0. Any genuine return
# visit therefore lands on >= 1 distinct day — that's enough to count as
# "came back", so we only nudge when the count is still 0.
TWIN_RETURN_MIN_DISTINCT_DAYS = 1

# Phase 4.6 Epic 2 — activation nudge ("chưa từng kích hoạt"). The biggest
# drop-off in the 6/2026 cohort is "0 tin nhắn": a user opens the bot /
# taps /start, then goes silent without ever finishing onboarding or
# sending a first message. We reach out first, inside a short activation
# window measured from when they opened the bot. The lower bound gives them
# a day to reply on their own; past the upper bound the generic
# silent-N-days triggers take over (a ``bot_started`` event counts as
# activity there), so this stays a focused first-touch nudge — never a
# perpetual one. Fires at most twice in the window (see cooldown in the
# trigger) so a genuinely dormant user isn't pestered.
ACTIVATION_NUDGE_MIN_DAYS = 1
ACTIVATION_NUDGE_MAX_DAYS = 7

# Event types that do NOT count as the user "activating". ``bot_started`` is
# the entry signal itself (opening the bot is not engagement); the empathy
# rows are our own outbound nudges. Any OTHER event — a button tap, a
# transaction, a miniapp open — means the user did something, so they're no
# longer in the "0 tin nhắn" cohort.
_NON_ACTIVATION_EVENT_TYPES = frozenset(
    {
        EventType.BOT_STARTED,
        EventType.EMPATHY_FIRED,
        EventType.EMPATHY_SENT,
    }
)

# Phase 4.7 Epic 1 — spending-drift warning cooldown. A drift is a slow,
# month-scale signal (baseline is a 3-window median), so a fortnight between
# nudges is long enough not to nag yet short enough to catch a pace that keeps
# climbing. Longer than the acute ``large_transaction`` (1 day) and the
# ``never_activated`` (3 days) triggers, matching ``user_silent_7_days``.
SPENDING_DRIFT_COOLDOWN_DAYS = 14


@dataclass(frozen=True)
class EmpathyTrigger:
    """Struct returned by a trigger check. Consumed by the engine orchestrator."""
    name: str
    priority: int          # lower = higher priority
    cooldown_days: int
    context: dict


async def check_all_triggers(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
    include_proactive: bool = True,
    include_activation_nudge: bool = False,
    include_drift: bool = False,
) -> Optional[EmpathyTrigger]:
    """Walk checks in priority order. Return first trigger not on cooldown.

    ``now`` override is for tests; production callers pass ``None``.

    ``include_proactive`` gates the Phase 4.4 proactive-companion trigger
    (``onboarding_no_twin_return``). ``include_activation_nudge`` gates the
    Phase 4.6 first-message trigger (``never_activated``). ``include_drift``
    gates the Phase 4.7 spending-drift trigger (``spending_drift``). The engine
    never reads env itself — the hourly job reads ``PROACTIVE_COMPANION_ENABLED``
    / ``ACTIVATION_NUDGE_ENABLED`` / ``DRIFT_WARNING_ENABLED`` and passes the
    decisions in, per the layer contract. When a flag is ``False`` its trigger
    is skipped while every pre-existing empathy trigger still fires.
    """
    now = now or datetime.now(timezone.utc)

    # Priority matters: acute signals (big spend) beat ambient ones
    # (silent N days) when both match on the same pass. The order of this
    # tuple IS the effective priority (we return the first match).
    checks = [
        _check_large_transaction,
        _check_payday_splurge,
        _check_over_budget_monthly,
    ]
    # A drift warning carries a concrete goal consequence, so it outranks the
    # ambient "come back" / silent-N-days nudges — but it stays below the acute
    # single-transaction signals above. Gated dark until the G1 gate + owner
    # sign-off (``DRIFT_WARNING_ENABLED``).
    if include_drift:
        checks.append(_check_spending_drift)
    if include_proactive:
        checks.append(_check_onboarding_no_twin_return)
    # The activation nudge owns the early window (1–7 days after opening the
    # bot) for never-activated users, so it must be checked BEFORE the
    # generic silent-N-days triggers — past day 7 its window closes and
    # ``user_silent_7_days`` naturally takes over.
    if include_activation_nudge:
        checks.append(_check_never_activated)
    checks.extend(
        (
            _check_user_silent_7_days,
            _check_user_silent_30_days,
            _check_weekend_high_spending,
            _check_first_saving_month,
            _check_consecutive_over_budget,
        )
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


async def _check_spending_drift(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """Current-window spend has drifted above the user's own recent baseline.

    Delegates the whole assessment — baseline median, dual threshold, and the
    Twin consequence — to ``drift_service.compute_drift`` (pure ``assess`` under
    a read-only gatherer). We fire only when it reports ``is_drifting``; the
    context carries a ``copy_variant`` so the copy renders the right shape:

    - ``delay``  — a goal slips a concrete number of months,
    - ``stall``  — the drift would erase the whole saving rate (goal stalls),
    - ``plain``  — drifting but no goal consequence to attach.

    The engine reads no env; ``DRIFT_WARNING_ENABLED`` is gated at the job edge
    and threaded in via ``include_drift``.
    """
    assessment = await drift_service.compute_drift(db, user, now=now)
    if assessment is None or not assessment.is_drifting:
        return None

    context: dict = {"drift": format_money_full(assessment.drift_amount)}
    if assessment.pace_unsustainable and assessment.goal_label:
        context["copy_variant"] = "stall"
        context["goal_label"] = assessment.goal_label
    elif assessment.goal_delay_months and assessment.goal_label:
        context["copy_variant"] = "delay"
        context["goal_label"] = assessment.goal_label
        context["goal_delay_months"] = assessment.goal_delay_months
    else:
        context["copy_variant"] = "plain"

    return EmpathyTrigger(
        name="spending_drift",
        priority=3,
        cooldown_days=SPENDING_DRIFT_COOLDOWN_DAYS,
        context=context,
    )


async def _check_onboarding_no_twin_return(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """Onboarded user who saw the Twin once but never came back to it.

    Fires inside the activation window
    (``ONBOARDING_SILENCE_MIN_DAYS`` … ``ONBOARDING_SILENCE_MAX_DAYS``
    days after ``onboarding_completed_at``) when the user has viewed the
    Twin on fewer than ``TWIN_RETURN_MIN_DISTINCT_DAYS`` distinct days —
    i.e. has not come back to look at it after onboarding. Past the window
    the generic silent-N-days triggers take over, so this stays a focused
    re-engagement nudge.
    """
    completed_at = user.onboarding_completed_at
    if completed_at is None:
        return None
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)

    days_since = (now - completed_at).days
    if not (ONBOARDING_SILENCE_MIN_DAYS <= days_since < ONBOARDING_SILENCE_MAX_DAYS):
        return None

    # Count distinct calendar days the user opened the Twin. Onboarding
    # writes no TwinViewEvent, so this starts at 0; a genuine return visit
    # is the first row, lifting the count to >= 1.
    distinct_days_stmt = select(
        func.count(func.distinct(func.date(TwinViewEvent.created_at)))
    ).where(TwinViewEvent.user_id == user.id)
    twin_view_days = int((await db.execute(distinct_days_stmt)).scalar_one() or 0)
    if twin_view_days >= TWIN_RETURN_MIN_DISTINCT_DAYS:
        return None

    return EmpathyTrigger(
        name="onboarding_no_twin_return",
        priority=3,
        cooldown_days=30,
        context={"days_since_onboarding": days_since},
    )


async def _check_never_activated(
    db: AsyncSession, user: User, now: datetime
) -> EmpathyTrigger | None:
    """User opened the bot but never activated — the "0 tin nhắn" cohort.

    Fires inside the activation window (``ACTIVATION_NUDGE_MIN_DAYS`` …
    ``ACTIVATION_NUDGE_MAX_DAYS`` days after the *first* ``bot_started``
    event) when the user:

    - has NOT finished onboarding (``onboarding_completed_at is None``), and
    - has no activity beyond opening the bot — no non-deleted expense and no
      event outside ``_NON_ACTIVATION_EVENT_TYPES``.

    Disjoint from ``onboarding_no_twin_return`` (which requires onboarding
    *completed*), so the two never fire for the same user. Past the window
    the generic silent-N-days triggers take over.
    """
    if user.onboarding_completed_at is not None:
        return None

    first_start_stmt = select(func.min(Event.timestamp)).where(
        Event.user_id == user.id,
        Event.event_type == EventType.BOT_STARTED,
    )
    first_start = (await db.execute(first_start_stmt)).scalar_one_or_none()
    if first_start is None:
        # No recorded bot open — outside this trigger's cohort.
        return None
    if first_start.tzinfo is None:
        first_start = first_start.replace(tzinfo=timezone.utc)

    days_since_start = (now - first_start).days
    if not (
        ACTIVATION_NUDGE_MIN_DAYS <= days_since_start < ACTIVATION_NUDGE_MAX_DAYS
    ):
        return None

    if await _has_activated(db, user.id):
        return None

    return EmpathyTrigger(
        name="never_activated",
        priority=2,
        cooldown_days=3,
        context={"days_since_start": days_since_start},
    )


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

async def _has_activated(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """True if the user did anything beyond opening the bot.

    "Activated" = logged a (non-deleted) expense OR produced any event
    outside ``_NON_ACTIVATION_EVENT_TYPES`` (which excludes the entry
    ``bot_started`` and our own empathy rows). Two cheap EXISTS-style
    scalar queries — the second short-circuits when the first already
    proves activation.
    """
    expense_stmt = (
        select(Expense.id)
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
        )
        .limit(1)
    )
    if (await db.execute(expense_stmt)).first() is not None:
        return True

    event_stmt = (
        select(Event.id)
        .where(
            Event.user_id == user_id,
            Event.event_type.notin_(_NON_ACTIVATION_EVENT_TYPES),
        )
        .limit(1)
    )
    return (await db.execute(event_stmt)).first() is not None


async def should_track_activation_reply(
    db: AsyncSession, user_id: uuid.UUID
) -> bool:
    """True if this user's message is their FIRST reply after a nudge.

    Powers the E2 #2.2 activation funnel: ``activation_nudge_sent``
    (Bé Tiền reached out first) vs ``activation_first_reply`` (the user
    answered). We only want to stamp the reply once, and only for a user
    we actually nudged — otherwise the funnel's denominator and numerator
    stop lining up.

    Returns True when a nudge WAS sent (``ACTIVATION_NUDGE_SENT`` row exists)
    and no reply has been recorded yet (``ACTIVATION_FIRST_REPLY`` absent).
    Env-free by design — the worker reads ``ACTIVATION_NUDGE_ENABLED`` at its
    edge and only calls this when the flag is on (layer contract). Two cheap
    limited scalar queries; the reply check short-circuits when no nudge was
    ever sent.
    """
    nudge_stmt = (
        select(Event.id)
        .where(
            Event.user_id == user_id,
            Event.event_type == EventType.ACTIVATION_NUDGE_SENT,
        )
        .limit(1)
    )
    if (await db.execute(nudge_stmt)).first() is None:
        return False

    reply_stmt = (
        select(Event.id)
        .where(
            Event.user_id == user_id,
            Event.event_type == EventType.ACTIVATION_FIRST_REPLY,
        )
        .limit(1)
    )
    return (await db.execute(reply_stmt)).first() is None


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

def render_message(
    trigger: EmpathyTrigger, user: User, *, tone: str | None = None
) -> str:
    """Pick a random variation from YAML and substitute placeholders.

    ``tone`` threads the tone dial (E4 #4.3). ``None`` (dial dark) renders the
    legacy ``empathy_messages.yaml`` copy exactly as before; a live
    ``"gentle"`` / ``"strict"`` consults ``tone_variants.yaml`` first and only
    falls back to the legacy copy when that trigger has no tone block yet. The
    ``TONE_DIAL_ENABLED`` flag is read by the hourly job, never here — the
    engine stays env-free.
    """
    salutation = salutation_of(user)
    variant = render_tone_variant(
        f"empathy.{trigger.name}",
        tone,
        salutation=salutation,
        name=user.get_greeting_name(),
        **trigger.context,
    )
    if variant is not None:
        return variant

    context = {
        "name": user.get_greeting_name(),
        "salutation": salutation,
        **trigger.context,
    }
    spec = _load_messages().get(trigger.name) or {}
    templates = spec.get("messages") or []
    # A trigger whose copy branches on the situation (e.g. ``spending_drift``:
    # delay / stall / plain) stores ``messages`` as a dict keyed by the
    # ``copy_variant`` the trigger put in its context, instead of a flat list.
    if isinstance(templates, dict):
        templates = templates.get(context.get("copy_variant")) or []
    if not templates:
        logger.warning("No empathy template for trigger %s", trigger.name)
        return ""

    template = random.choice(templates)
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
