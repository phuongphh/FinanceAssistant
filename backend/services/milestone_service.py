"""Milestone detection and celebration rendering (Phase 2, Issue #39).

The daily scheduler (`backend/jobs/check_milestones.py`) calls
`detect_and_record(user_id)` each morning. For every fresh
`UserMilestone` created, it then calls `get_celebration_message(...)`
to load a random variation from `content/milestone_messages.yaml`,
renders placeholders, and sends it via Telegram.

Scope of this implementation (per Phase 2 exit criteria, option b):
- Fully implemented: time milestones (7/30/100/365 days),
  first_transaction, streak milestones (7/30/100).
- Stubbed with clear hooks: savings milestones and first_voice/
  first_photo behaviour milestones. These return [] for now so the
  job runs cleanly; wiring the actual detection is tracked
  separately once income + voice/photo ingestion land.

Deduplication: `(user_id, milestone_type)` is a DB unique constraint;
this service uses `INSERT ... ON CONFLICT DO NOTHING` semantics by
checking first and swallowing IntegrityError as a safety net.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full
from backend.models.expense import Expense
from backend.models.streak import UserStreak
from backend.models.user import User
from backend.models.user_milestone import MilestoneType, UserMilestone
from backend.wealth import ladder
from backend.wealth.services.net_worth_calculator import calculate as calculate_net_worth

logger = logging.getLogger(__name__)

_MESSAGES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "content"
    / "milestone_messages.yaml"
)


# In-module cache so the YAML is parsed once per process.
_messages_cache: dict[str, list[str]] | None = None


def _load_messages() -> dict[str, list[str]]:
    global _messages_cache
    if _messages_cache is None:
        with open(_MESSAGES_PATH, encoding="utf-8") as f:
            _messages_cache = yaml.safe_load(f) or {}
    return _messages_cache


def reload_messages_for_tests() -> None:
    """Drop the YAML cache — used by unit tests that stub the file."""
    global _messages_cache
    _messages_cache = None


# --- Detection -------------------------------------------------------

_DAY_THRESHOLDS: dict[int, str] = {
    7: MilestoneType.DAYS_7,
    30: MilestoneType.DAYS_30,
    100: MilestoneType.DAYS_100,
    365: MilestoneType.DAYS_365,
}

_STREAK_THRESHOLDS: dict[int, str] = {
    7: MilestoneType.STREAK_7,
    30: MilestoneType.STREAK_30,
    100: MilestoneType.STREAK_100,
}


async def detect_and_record(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserMilestone]:
    """Run every detection rule, persist new hits, return them.

    The returned list only contains rows that were freshly created in
    this call — ones that haven't been celebrated yet.
    """
    new_rows: list[UserMilestone] = []
    new_rows.extend(await _check_first_transaction(db, user_id))
    new_rows.extend(await _check_time_milestones(db, user_id))
    new_rows.extend(await _check_streak_milestones(db, user_id))
    new_rows.extend(await _check_wealth_level_changes(db, user_id))
    # Savings + behavior detection deferred — see module docstring.
    new_rows.extend(await _check_savings_milestones(db, user_id))
    new_rows.extend(await _check_behavior_milestones(db, user_id))
    return new_rows


async def _existing_types(
    db: AsyncSession, user_id: uuid.UUID
) -> set[str]:
    stmt = select(UserMilestone.milestone_type).where(
        UserMilestone.user_id == user_id
    )
    return {r[0] for r in (await db.execute(stmt)).all()}


async def _create_if_missing(
    db: AsyncSession,
    user_id: uuid.UUID,
    milestone_type: str,
    extra: dict | None = None,
    existing: set[str] | None = None,
) -> UserMilestone | None:
    """Insert one milestone if we haven't recorded this type yet.

    Uses Postgres ``INSERT ... ON CONFLICT (user_id, milestone_type)
    DO NOTHING`` with ``RETURNING`` — atomic dedup against concurrent
    inserts from another worker without needing a per-row commit.
    Returns the row we inserted, or ``None`` if another worker won.

    TRANSACTION_OWNED_BY_CALLER — the scheduler/job commits once at the
    end of its unit of work. Previously this service committed per row
    so a later IntegrityError wouldn't roll back earlier milestones;
    with ON CONFLICT that class of error disappears entirely.
    """
    if existing is not None and milestone_type in existing:
        return None

    values = {
        "user_id": user_id,
        "milestone_type": milestone_type,
        "achieved_at": datetime.now(timezone.utc),
        "extra": extra or {},
    }
    stmt = (
        pg_insert(UserMilestone)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["user_id", "milestone_type"])
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        # Conflict — another worker (or an earlier pass in this run)
        # already persisted this milestone type.
        return None
    if existing is not None:
        existing.add(milestone_type)
    # Return a representation of what we inserted. Not attached to the
    # session — the caller (check_milestones job) re-queries via
    # ``get_uncelebrated`` before sending, so it reads the persisted
    # row with all server-side defaults (id, achieved_at).
    return UserMilestone(
        user_id=user_id,
        milestone_type=milestone_type,
        extra=extra or {},
    )


async def _check_time_milestones(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserMilestone]:
    user = await db.get(User, user_id)
    if not user or not user.created_at:
        return []

    created = user.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    days_since = (datetime.now(timezone.utc) - created).days

    existing = await _existing_types(db, user_id)
    out: list[UserMilestone] = []
    for threshold, m_type in sorted(_DAY_THRESHOLDS.items()):
        if days_since >= threshold:
            row = await _create_if_missing(
                db, user_id, m_type,
                extra={"days": days_since},
                existing=existing,
            )
            if row:
                out.append(row)
    return out


async def _check_first_transaction(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserMilestone]:
    existing = await _existing_types(db, user_id)
    if MilestoneType.FIRST_TRANSACTION in existing:
        return []

    count_stmt = select(func.count()).select_from(Expense).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
    )
    count = (await db.execute(count_stmt)).scalar_one()
    if count <= 0:
        return []

    row = await _create_if_missing(
        db, user_id, MilestoneType.FIRST_TRANSACTION,
        extra={"count": int(count)},
        existing=existing,
    )
    return [row] if row else []


async def _check_streak_milestones(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserMilestone]:
    streak = await db.get(UserStreak, user_id)
    if not streak:
        return []

    # Celebrate the longest streak the user has ever held (so that
    # re-hitting a threshold after a break doesn't mint a duplicate
    # row — the unique constraint already prevents that, but using
    # longest_streak makes intent clearer).
    watermark = max(streak.longest_streak or 0, streak.current_streak or 0)

    existing = await _existing_types(db, user_id)
    out: list[UserMilestone] = []
    for threshold, m_type in sorted(_STREAK_THRESHOLDS.items()):
        if watermark >= threshold:
            row = await _create_if_missing(
                db, user_id, m_type,
                extra={"streak": watermark},
                existing=existing,
            )
            if row:
                out.append(row)
    return out


# Mapping: each non-Starter level has its own UP milestone code; each
# non-HNW level has its own DOWN milestone code. Lookup tables keep
# `_check_wealth_level_changes` linear and obvious.
_UP_MILESTONE_BY_LEVEL: dict[ladder.WealthLevel, str] = {
    ladder.WealthLevel.YOUNG_PROFESSIONAL: MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF,
    ladder.WealthLevel.MASS_AFFLUENT: MilestoneType.WEALTH_LEVEL_UP_MASS_AFFLUENT,
    ladder.WealthLevel.HIGH_NET_WORTH: MilestoneType.WEALTH_LEVEL_UP_HNW,
}
_DOWN_MILESTONE_BY_LEVEL: dict[ladder.WealthLevel, str] = {
    ladder.WealthLevel.STARTER: MilestoneType.WEALTH_LEVEL_DOWN_STARTER,
    ladder.WealthLevel.YOUNG_PROFESSIONAL: MilestoneType.WEALTH_LEVEL_DOWN_YOUNG_PROF,
    ladder.WealthLevel.MASS_AFFLUENT: MilestoneType.WEALTH_LEVEL_DOWN_MASS_AFFLUENT,
}


async def _check_wealth_level_changes(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserMilestone]:
    """Detect wealth-band crossings (Issue #155).

    Strategy:
    - User's *highest level ever* is reconstructed from existing UP
      milestones (Starter is the implicit floor).
    - If current level > highest_ever → fire UP milestone for current.
    - If current level < highest_ever → fire DOWN milestone for current.
      Done with empathy in YAML — never blame.
    - Yo-yo across a boundary is dedup'd by ``(user_id, milestone_type)``
      unique constraint, so re-crossing fires no second message.

    Net worth is recomputed here (rather than trusting the persisted
    ``user.wealth_level``) so the milestone reflects truth at job time —
    asset values may have drifted since the last write.
    """
    user = await db.get(User, user_id)
    if user is None:
        return []

    breakdown = await calculate_net_worth(db, user_id)
    current_level = ladder.detect_level(breakdown.total)

    existing = await _existing_types(db, user_id)
    highest_idx = ladder.LEVEL_ORDER.index(ladder.WealthLevel.STARTER)
    for level, m_type in _UP_MILESTONE_BY_LEVEL.items():
        if m_type in existing:
            highest_idx = max(highest_idx, ladder.LEVEL_ORDER.index(level))

    current_idx = ladder.LEVEL_ORDER.index(current_level)
    if current_idx == highest_idx:
        return []

    if current_idx > highest_idx:
        m_type = _UP_MILESTONE_BY_LEVEL.get(current_level)
    else:
        m_type = _DOWN_MILESTONE_BY_LEVEL.get(current_level)

    if not m_type:
        return []  # Defensive: STARTER has no UP, HNW has no DOWN.

    target_amount, target_level = ladder.next_milestone(breakdown.total)
    extra = {
        "new_level": current_level.value,
        "next_target_amount": str(target_amount),
        "next_level": target_level.value,
    }
    row = await _create_if_missing(
        db, user_id, m_type, extra=extra, existing=existing
    )
    return [row] if row else []


async def _check_savings_milestones(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserMilestone]:
    """Stub — savings detection needs income + expense aggregation.

    Kept as a hook so the daily scheduler can call this without
    changing its shape once we wire the real logic. Returns [] today.
    """
    return []


async def _check_behavior_milestones(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserMilestone]:
    """Stub — first_voice / first_photo / first_budget detection.

    Will be wired once voice + photo ingestion events are reliably
    persisted. Returns [] today.
    """
    return []


# --- Rendering -------------------------------------------------------

async def get_celebration_message(
    milestone: UserMilestone, user: User
) -> str:
    """Load YAML, pick a random variation, render placeholders."""
    messages = _load_messages()
    templates = messages.get(milestone.milestone_type) or []
    if not templates:
        logger.warning(
            "No milestone template for type %s", milestone.milestone_type
        )
        return ""

    template = random.choice(templates)
    context = _render_context(milestone, user)
    try:
        return template.format(**context)
    except KeyError as exc:
        logger.warning(
            "Milestone %s missing placeholder %s", milestone.milestone_type, exc
        )
        return template  # Unrendered is still better than nothing.


def _render_context(milestone: UserMilestone, user: User) -> dict:
    extra = milestone.extra or {}
    amount_raw = extra.get("amount")
    amount_str = (
        format_money_full(float(amount_raw)) if amount_raw is not None else ""
    )

    # Wealth-level placeholders (Issue #155). Empty strings when missing
    # so non-wealth templates that don't reference them still render.
    level_label = level_full = next_target = next_level_label = ""
    new_level_raw = extra.get("new_level")
    next_level_raw = extra.get("next_level")
    next_target_raw = extra.get("next_target_amount")
    if new_level_raw:
        try:
            level = ladder.WealthLevel(new_level_raw)
            level_label = ladder.format_level(level, "short")
            level_full = ladder.format_level(level, "full")
        except ValueError:
            logger.warning("Unknown wealth level %s in milestone extra", new_level_raw)
    if next_level_raw:
        try:
            n_level = ladder.WealthLevel(next_level_raw)
            next_level_label = ladder.format_level(n_level, "short")
        except ValueError:
            logger.warning("Unknown next level %s in milestone extra", next_level_raw)
    if next_target_raw is not None:
        try:
            next_target = format_money_full(float(next_target_raw))
        except (TypeError, ValueError):
            pass

    return {
        "name": user.get_greeting_name(),
        "days": extra.get("days", 0),
        "count": extra.get("count", 0),
        "amount": amount_str,
        "goal_progress": extra.get("goal_progress", ""),
        "level_label": level_label,
        "level_full": level_full,
        "next_target": next_target,
        "next_level_label": next_level_label,
    }


async def mark_celebrated(
    db: AsyncSession, milestone_id: uuid.UUID
) -> None:
    """Stamp celebrated_at. TRANSACTION_OWNED_BY_CALLER — caller must
    commit after each call so a later Telegram-send failure doesn't
    roll back earlier celebrations."""
    row = await db.get(UserMilestone, milestone_id)
    if not row:
        return
    row.celebrated_at = datetime.now(timezone.utc)
    await db.flush()


async def get_uncelebrated(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserMilestone]:
    """All milestones for a user that haven't been celebrated yet.

    Includes both rows created in the current run and stragglers from
    previous runs (e.g. skipped by the per-user daily cap or left
    un-marked after a failed Telegram send). Ordered by ``achieved_at``
    so the oldest misses get priority when the cap triggers again.
    """
    stmt = (
        select(UserMilestone)
        .where(
            UserMilestone.user_id == user_id,
            UserMilestone.celebrated_at.is_(None),
        )
        .order_by(UserMilestone.achieved_at.asc())
    )
    return list((await db.execute(stmt)).scalars())
