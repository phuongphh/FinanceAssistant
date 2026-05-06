"""Nightly cron — auto-detect recurring patterns + deliver suggestions.

Phase 3.8 Epic 3 (Story P3.8-S8). Schedule from ``backend.scheduler``:
runs once a day at 02:00 Asia/Ho_Chi_Minh (low-activity window so
the Telegram delivery doesn't compete with morning briefings).

For each active user with ≥3 months of expense history:
1. Run ``recurring_detector.detect_patterns``.
2. Persist top-3 candidates to ``pattern_suggestions_log`` (rate-
   limited to 3/week per user).
3. Deliver each as a Telegram message with confirm/reject keyboard.

Single transaction per user — if the Telegram send fails, we ROLL
BACK the log row so the same suggestion can be retried tomorrow
(otherwise the rate-limit counter would tick without delivery).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from backend.bot.keyboards.recurring_keyboard import suggestion_keyboard
from backend.database import get_session_factory
from backend.models.user import User
from backend.services import recurring_detector
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)


# Stay aligned with detector's heuristic: only run for users with
# enough history to make detection meaningful.
MIN_HISTORY_DAYS = 90


async def run_recurring_detection() -> None:
    """Entry point for the APScheduler cron registration."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        users = await _eligible_users(db)
    logger.info("recurring detection: %d eligible users", len(users))

    for user in users:
        # New session per user so a single user's failure doesn't
        # poison the rest. Mirrors the morning_briefing_job pattern.
        async with session_factory() as user_db:
            try:
                await _run_for_user(user_db, user)
                await user_db.commit()
            except Exception:
                await user_db.rollback()
                logger.exception(
                    "recurring detection failed for user %s", user.id,
                )


async def _eligible_users(db) -> list[User]:
    """Active users (not deleted) with at least 90 days since
    creation. Brand-new users have no history to mine yet."""
    cutoff = datetime.utcnow() - timedelta(days=MIN_HISTORY_DAYS)
    stmt = (
        select(User)
        .where(
            User.created_at <= cutoff,
            User.deleted_at.is_(None),
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def _run_for_user(db, user: User) -> None:
    suggestions = await recurring_detector.detect_patterns(db, user.id)
    if not suggestions:
        return
    saved = await recurring_detector.persist_and_deliver(
        db, user.id, suggestions,
    )
    for log_row, suggestion in zip(saved, suggestions):
        try:
            await send_message(
                chat_id=user.telegram_id,
                text=recurring_detector.format_suggestion_message(suggestion),
                parse_mode="HTML",
                reply_markup=suggestion_keyboard(log_row.id),
            )
        except Exception:
            # Re-raise so the per-user transaction rolls back —
            # we don't want the rate-limit counter to tick without
            # the user actually seeing the suggestion.
            logger.exception("failed to send suggestion to user %s", user.id)
            raise
