"""Hourly empathy-trigger check — Phase 2, Issue #40.

Runs once per hour (APScheduler registers it in ``backend/scheduler.py``).
Quiet-hours (22:00 – 07:00 Asia/Ho_Chi_Minh) guard lives inside this job
rather than in the scheduler so a misconfigured cron can't start blasting
messages at 3am.

Per run, for each active user:
1. Skip if the user already hit the daily cap (2 messages / user / day).
2. Ask the empathy engine for a trigger not on cooldown.
3. Render the YAML-templated message and send it via Telegram.
4. On successful send, stamp an ``empathy_fired`` event so the cooldown
   and cap queries see it next pass.

Error isolation: per-user try/except keeps one failure from killing the
whole loop. Rate-limited between users to stay well under Telegram's
30-messages-per-second global flood limit even when we scale to 1k users.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from backend import analytics
from backend.analytics import EventType
from backend.bot.personality import empathy_engine
from backend.database import get_session_factory
from backend.jobs._active_users import get_active_users
from backend.models.user import User
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

# Max messages per user per day. Empathy at the right time = care;
# two of them on the same day = pressure. Keep it tight.
MAX_EMPATHY_PER_USER_PER_DAY = 2

# Seconds between users — ~2s × 1k users = 33 min, well inside the
# hourly window and well under Telegram's flood limit.
INTER_USER_DELAY_SECONDS = 2.0

# Look back this many days for "active" users. Longer window than
# milestones (30d) so we can still send a "haven't seen you in 30 days"
# message to someone who just crossed the threshold.
ACTIVE_WINDOW_DAYS = 60

# Quiet hours in the user's local timezone — empathy messages at 3am
# read as spam, not care.
QUIET_HOURS_START = time(22, 0)
QUIET_HOURS_END = time(7, 0)
LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _is_quiet_hour(now_local: datetime) -> bool:
    t = now_local.time()
    # Window wraps midnight: 22:00 <= t OR t < 07:00
    return t >= QUIET_HOURS_START or t < QUIET_HOURS_END


async def run_hourly_empathy_check(now: datetime | None = None) -> None:
    """Entry point for the scheduler. ``now`` override supports tests."""
    now_utc = now or datetime.now(timezone.utc)
    now_local = now_utc.astimezone(LOCAL_TZ)
    if _is_quiet_hour(now_local):
        logger.debug(
            "empathy-check: quiet hours (%s) — skipping run",
            now_local.strftime("%H:%M"),
        )
        return

    session_factory = get_session_factory()
    async with session_factory() as db:
        users = await get_active_users(db, days=ACTIVE_WINDOW_DAYS)

    logger.info("empathy-check: scanning %d active users", len(users))

    for user in users:
        try:
            await _process_user(user, now=now_utc)
        except Exception:
            logger.exception(
                "empathy-check: user %s failed — continuing", user.id
            )
        await asyncio.sleep(INTER_USER_DELAY_SECONDS)


async def _process_user(user: User, *, now: datetime) -> None:
    """Check, send, and record one empathy trigger for a single user."""
    session_factory = get_session_factory()

    async with session_factory() as db:
        # 1. Daily cap check first — cheaper than running all triggers.
        today_count = await empathy_engine.count_empathy_fired_today(
            db, user.id, now=now
        )
        if today_count >= MAX_EMPATHY_PER_USER_PER_DAY:
            logger.debug(
                "empathy-check: user=%s at daily cap (%d); skipping",
                user.id, today_count,
            )
            return

        trigger = await empathy_engine.check_all_triggers(db, user, now=now)
        if not trigger:
            return

        message = empathy_engine.render_message(trigger, user)
        if not message:
            return
        if not user.telegram_id:
            return

        # 2. Send FIRST — then stamp the event. If we stamped before
        # sending and the Telegram call failed, the cooldown would lock
        # us out from retrying even though the user never heard us.
        result = await send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode="HTML",
        )
        if result is None:
            logger.warning(
                "empathy-check: send failed for user=%s trigger=%s",
                user.id, trigger.name,
            )
            return

        await empathy_engine.record_fired(db, user.id, trigger.name, now=now)
        await db.commit()

        analytics.track(
            EventType.EMPATHY_SENT,
            user_id=user.id,
            properties={"trigger": trigger.name},
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_hourly_empathy_check())
