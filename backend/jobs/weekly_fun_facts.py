"""Weekly fun-fact sender — Phase 2, Issue #42.

Runs every Sunday at 19:00 Asia/Ho_Chi_Minh (registered in
``backend/scheduler.py``). For each user active in the last 14 days,
generates one data-driven fact and sends it via Telegram.

Dedup + cap choices
- "Active in last 14 days" instead of 7, so someone who logs only
  weekly isn't always missed.
- Stamps ``fun_fact_sent`` in the ``events`` table with the fact key so
  analytics can see which fact types resonate.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from backend.analytics import EventType
from backend.bot.personality import fun_facts
from backend.database import get_session_factory
from backend.jobs._active_users import get_active_users
from backend.models.event import Event
from backend.models.user import User
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

INTER_USER_DELAY_SECONDS = 1.0
ACTIVE_WINDOW_DAYS = 14


async def run_weekly_fun_facts() -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        users = await get_active_users(db, days=ACTIVE_WINDOW_DAYS)

    logger.info("fun-facts: scanning %d active users", len(users))

    for user in users:
        try:
            await _process_user(user)
        except Exception:
            logger.exception(
                "fun-facts: user %s failed — continuing", user.id
            )
        await asyncio.sleep(INTER_USER_DELAY_SECONDS)


async def _process_user(user: User) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        fact = await fun_facts.generate_for_user(db, user)
        if fact is None:
            # User has no data this week — silent is better than generic.
            return
        if not user.telegram_id:
            return

        result = await send_message(
            chat_id=user.telegram_id,
            text=fact.text,
            parse_mode="HTML",
        )
        if result is None:
            logger.warning(
                "fun-facts: send failed for user=%s key=%s",
                user.id, fact.key,
            )
            return

        # Single insert serves both dedup/audit and analytics — writing
        # via `analytics.track` too would double-count every send in the
        # events table.
        db.add(
            Event(
                user_id=user.id,
                event_type=EventType.FUN_FACT_SENT,
                properties={"key": fact.key},
                timestamp=datetime.now(timezone.utc),
            )
        )
        await db.commit()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_weekly_fun_facts())
