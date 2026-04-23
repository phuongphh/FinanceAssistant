"""Weekly goal reminder — Phase 2, Issue #44.

Runs every Monday at 08:30 Asia/Ho_Chi_Minh. Sends each user who
completed onboarding a reminder tied to the ``primary_goal`` they
chose, referencing *last week's* data for personal context.

Skip rules applied in ``memory_moments.render_goal_reminder``:
- no primary_goal  → skip
- inactive last 7d → skip (nothing honest to reference)
- reach_goal but no active Goal row → skip
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select

from backend import analytics
from backend.analytics import EventType
from backend.bot.personality import memory_moments
from backend.database import get_session_factory
from backend.models.user import User
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

INTER_USER_DELAY_SECONDS = 1.0


async def run_weekly_goal_reminder(today: date | None = None) -> None:
    today = today or date.today()
    session_factory = get_session_factory()
    async with session_factory() as db:
        # Candidates: onboarded, active, with a primary_goal, with a telegram_id.
        stmt = select(User).where(
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            User.telegram_id.isnot(None),
            User.primary_goal.isnot(None),
            User.onboarding_completed_at.isnot(None),
        )
        users = list((await db.execute(stmt)).scalars())

    logger.info("goal-reminder: scanning %d onboarded users", len(users))

    for user in users:
        try:
            await _process_user(user, today=today)
        except Exception:
            logger.exception(
                "goal-reminder: user %s failed — continuing", user.id
            )
        await asyncio.sleep(INTER_USER_DELAY_SECONDS)


async def _process_user(user: User, *, today: date) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        message = await memory_moments.render_goal_reminder(
            db, user, today=today
        )
        if not message:
            return
        if not user.telegram_id:
            return

        result = await send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode="HTML",
        )
        if result is None:
            logger.warning(
                "goal-reminder: send failed user=%s goal=%s",
                user.id, user.primary_goal,
            )
            return

        analytics.track(
            EventType.GOAL_REMINDER_SENT,
            user_id=user.id,
            properties={"goal": user.primary_goal},
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_weekly_goal_reminder())
