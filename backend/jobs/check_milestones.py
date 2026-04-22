"""Daily milestone check — runs 08:00 Asia/Ho_Chi_Minh.

Loops over every recently-active user, asks the milestone service to
detect and record fresh achievements, then sends a celebration
message via Telegram and stamps `celebrated_at`.

Caps:
- Max 2 celebration messages per user per run to avoid bursts
  (streak + time milestone on the same day, for example).
- 1-second pause between users to stay under Telegram's flood limits.
- Per-user try/except so one failure doesn't halt the loop.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.database import get_session_factory
from backend.models.expense import Expense
from backend.models.user import User
from backend.models.user_milestone import UserMilestone
from backend.services import milestone_service
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_USER_PER_DAY = 2
INTER_USER_DELAY_SECONDS = 1.0
ACTIVE_WINDOW_DAYS = 30


async def _active_user_ids(
    db: AsyncSession, since: datetime
) -> list[User]:
    """Users with at least one non-deleted expense in the window."""
    active_ids_stmt = select(distinct(Expense.user_id)).where(
        Expense.created_at >= since,
        Expense.deleted_at.is_(None),
    )
    user_ids = [r[0] for r in (await db.execute(active_ids_stmt)).all()]
    if not user_ids:
        return []
    users_stmt = select(User).where(
        User.id.in_(user_ids),
        User.deleted_at.is_(None),
        User.is_active.is_(True),
    )
    return list((await db.execute(users_stmt)).scalars())


async def run_daily_milestone_check() -> None:
    session_factory = get_session_factory()
    since = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WINDOW_DAYS)

    async with session_factory() as db:
        users = await _active_user_ids(db, since)

    logger.info("milestone-check: scanning %d active users", len(users))

    for user in users:
        try:
            await _process_user(user)
        except Exception:
            logger.exception(
                "milestone-check: user %s failed — continuing", user.id
            )
        await asyncio.sleep(INTER_USER_DELAY_SECONDS)


async def _process_user(user: User) -> None:
    session_factory = get_session_factory()
    sent_this_run = 0

    async with session_factory() as db:
        new_rows: list[UserMilestone] = await milestone_service.detect_and_record(
            db, user.id
        )

        for milestone in new_rows:
            if sent_this_run >= MAX_MESSAGES_PER_USER_PER_DAY:
                logger.debug(
                    "milestone-check: reached per-user cap for %s", user.id
                )
                break

            message = await milestone_service.get_celebration_message(
                milestone, user
            )
            if not message:
                continue
            if not user.telegram_id:
                continue

            await send_message(
                chat_id=user.telegram_id,
                text=message,
                parse_mode="HTML",
            )
            await milestone_service.mark_celebrated(db, milestone.id)
            sent_this_run += 1

            analytics.track(
                "milestone_celebrated",
                user_id=user.id,
                properties={"type": milestone.milestone_type},
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_daily_milestone_check())
