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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full
from backend.models.expense import Expense
from backend.models.streak import UserStreak
from backend.models.user import User
from backend.models.user_milestone import MilestoneType, UserMilestone

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
    if existing is not None and milestone_type in existing:
        return None
    row = UserMilestone(
        user_id=user_id,
        milestone_type=milestone_type,
        achieved_at=datetime.now(timezone.utc),
        extra=extra or {},
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except IntegrityError:
        # Race with another worker — someone else already recorded it.
        await db.rollback()
        return None
    if existing is not None:
        existing.add(milestone_type)
    return row


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
    return {
        "name": user.get_greeting_name(),
        "days": extra.get("days", 0),
        "count": extra.get("count", 0),
        "amount": amount_str,
        "goal_progress": extra.get("goal_progress", ""),
    }


async def mark_celebrated(
    db: AsyncSession, milestone_id: uuid.UUID
) -> None:
    row = await db.get(UserMilestone, milestone_id)
    if not row:
        return
    row.celebrated_at = datetime.now(timezone.utc)
    await db.commit()


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
