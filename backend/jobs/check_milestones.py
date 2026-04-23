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

from backend import analytics
from backend.database import get_session_factory
from backend.jobs._active_users import get_active_users
from backend.models.user import User
from backend.models.user_milestone import UserMilestone
from backend.services import milestone_service
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_USER_PER_DAY = 2
INTER_USER_DELAY_SECONDS = 1.0
ACTIVE_WINDOW_DAYS = 30


async def run_daily_milestone_check() -> None:
    session_factory = get_session_factory()

    async with session_factory() as db:
        users = await get_active_users(
            db, days=ACTIVE_WINDOW_DAYS,
            require_telegram_id=False,  # milestone job tolerates missing tg_id
        )

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
        # 1. Detect and persist any newly-achieved milestones. The
        #    service flushes but doesn't commit — persist the batch as
        #    one transaction so either all new milestones land or none
        #    do. Uses INSERT ... ON CONFLICT so partial re-runs are safe.
        await milestone_service.detect_and_record(db, user.id)
        await db.commit()

        # 2. Iterate over every uncelebrated row — both the ones we
        #    just inserted and stragglers from previous runs that
        #    were skipped by the daily cap or left un-marked after a
        #    failed Telegram send. Oldest first so mis-delivered rows
        #    drain before new ones.
        pending: list[UserMilestone] = await milestone_service.get_uncelebrated(
            db, user.id
        )

        for milestone in pending:
            if sent_this_run >= MAX_MESSAGES_PER_USER_PER_DAY:
                logger.debug(
                    "milestone-check: reached per-user cap for %s; "
                    "%d pending left for next run",
                    user.id, len(pending) - sent_this_run,
                )
                break

            message = await milestone_service.get_celebration_message(
                milestone, user
            )
            if not message:
                continue
            if not user.telegram_id:
                continue

            result = await send_message(
                chat_id=user.telegram_id,
                text=message,
                parse_mode="HTML",
            )
            # `send_message` returns None on API errors without
            # raising — treat a missing result as a failed delivery
            # and leave `celebrated_at` NULL so the next run retries.
            if result is None:
                logger.warning(
                    "milestone-check: send failed for user=%s type=%s — "
                    "will retry next run",
                    user.id, milestone.milestone_type,
                )
                continue

            await milestone_service.mark_celebrated(db, milestone.id)
            # Commit per-iteration: the Telegram send above is an
            # external side effect we can't undo. If the NEXT send
            # fails, we still want this celebration persisted so the
            # retry logic doesn't double-deliver.
            await db.commit()
            sent_this_run += 1

            analytics.track(
                analytics.EventType.MILESTONE_CELEBRATED,
                user_id=user.id,
                properties={"type": milestone.milestone_type},
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_daily_milestone_check())
