"""Streak tracking — Phase 2, Issue #41.

One row per user in ``user_streaks`` (see
``backend/models/streak.py``). ``record_activity`` is called from the
expense-creation path so the streak updates inside the same transaction
as the expense itself — an expense can't exist without its streak side-
effect, and vice versa.

Design
------
- **Idempotent per-day**: calling ``record_activity`` multiple times in
  the same local day no-ops after the first call. Users logging 5
  receipts today must see streak stay at the same number.
- **Local-day semantics**: "yesterday/today" are computed in the user's
  timezone (``User.timezone``, default ``Asia/Ho_Chi_Minh``). A user in
  Vietnam logging at 23:55 and another log at 00:05 should count as a
  streak-continuing pair, not a reset, because they're on different UTC
  days but the same local day boundary logic expects different days.
- **No over-gamify**: we emit ``is_milestone`` only at 7 / 30 / 100 /
  365. No XP, no levels, no leaderboards. This is a finance app, not
  Duolingo (docs/strategy/phase-2-detailed.md §3.1).
- **TRANSACTION_OWNED_BY_CALLER**: no ``db.commit()`` here. The caller
  (router/worker) owns the transaction boundary per the layer contract
  in CLAUDE.md §0.1.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.streak import UserStreak
from backend.models.user import User

logger = logging.getLogger(__name__)

# Streak lengths that trigger milestone celebrations. Aligned with
# MilestoneType.STREAK_7 / STREAK_30 / STREAK_100 (see user_milestone.py).
# 365 is here too — the YAML has copy for it via days_365 if we want to
# wire it in future; for now it's celebrated via the streak channel.
STREAK_MILESTONE_THRESHOLDS: frozenset[int] = frozenset({7, 30, 100, 365})


@dataclass(frozen=True)
class StreakResult:
    """Return value of ``record_activity`` — consumable by handlers."""
    current: int
    longest: int
    streak_continued: bool  # True when current advanced or initialised on this call
    is_milestone: bool      # True when ``current`` hits one of the thresholds

    def as_dict(self) -> dict:
        return {
            "current": self.current,
            "longest": self.longest,
            "streak_continued": self.streak_continued,
            "is_milestone": self.is_milestone,
        }


def _today_in_tz(tz_name: str | None) -> date:
    """Today's date in the user's timezone, with graceful fallback."""
    try:
        tz = ZoneInfo(tz_name or "Asia/Ho_Chi_Minh")
    except Exception:
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
    return datetime.now(tz).date()


async def record_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    today: date | None = None,
) -> StreakResult:
    """Register one activity (typically: an expense just got created).

    Returns a ``StreakResult`` describing the outcome. The caller can
    use ``is_milestone`` to kick off a celebration.

    ``today`` override is for tests.
    """
    user = await db.get(User, user_id)
    tz_today = today or _today_in_tz(user.timezone if user else None)

    streak = await db.get(UserStreak, user_id)
    if streak is None:
        # First activity ever — seed with streak=1. Use INSERT ... ON
        # CONFLICT DO NOTHING so two concurrent expense saves don't both
        # try to insert the same user and raise.
        stmt = (
            pg_insert(UserStreak)
            .values(
                user_id=user_id,
                current_streak=1,
                longest_streak=1,
                last_active_date=tz_today,
            )
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await db.execute(stmt)
        # Re-read so we return the row that actually landed (ours or the
        # concurrent writer's — either way current=1 after this).
        streak = await db.get(UserStreak, user_id)
        if streak is None:
            # Shouldn't happen, but be defensive rather than crash a
            # transaction flow.
            logger.warning("record_activity: streak row missing after upsert for %s", user_id)
            return StreakResult(
                current=1, longest=1, streak_continued=True,
                is_milestone=1 in STREAK_MILESTONE_THRESHOLDS,
            )
        await db.flush()
        return StreakResult(
            current=streak.current_streak,
            longest=streak.longest_streak,
            streak_continued=True,
            is_milestone=streak.current_streak in STREAK_MILESTONE_THRESHOLDS,
        )

    last = streak.last_active_date
    if last == tz_today:
        # Already logged today — idempotent. Caller can still read the
        # current streak but `streak_continued=False` signals "no-op".
        return StreakResult(
            current=streak.current_streak,
            longest=streak.longest_streak,
            streak_continued=False,
            is_milestone=False,
        )

    if last == tz_today - timedelta(days=1):
        streak.current_streak += 1
    else:
        # Gap > 1 day, or this is a backfilled entry from before last
        # (shouldn't happen in production but don't crash). Reset.
        streak.current_streak = 1

    if streak.current_streak > streak.longest_streak:
        streak.longest_streak = streak.current_streak
    streak.last_active_date = tz_today

    await db.flush()
    return StreakResult(
        current=streak.current_streak,
        longest=streak.longest_streak,
        streak_continued=True,
        is_milestone=streak.current_streak in STREAK_MILESTONE_THRESHOLDS,
    )


async def get_streak(
    db: AsyncSession, user_id: uuid.UUID
) -> UserStreak | None:
    """Read-only streak fetch for display paths (daily summary, /stats)."""
    return await db.get(UserStreak, user_id)
