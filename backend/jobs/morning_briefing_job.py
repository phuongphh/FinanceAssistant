"""Morning briefing scheduler — runs every 15 minutes.

Each run looks for users whose ``briefing_time`` falls in the next
15-minute window in Asia/Ho_Chi_Minh, generates a personalised
briefing via :class:`BriefingFormatter`, and dispatches it through
the :class:`Notifier` port. The 15-minute cadence (rather than a
single 7 AM cron) lets users pick custom times like 06:30 or 08:15
without us re-deploying scheduler config.

Dedup strategy
--------------
A briefing has been sent today iff there is a
``MORNING_BRIEFING_SENT`` event for the user with a timestamp
≥ today's 00:00 in their timezone. Events are append-only so this
also covers retries inside the same run (we mark sent after a
successful send, before the next user).

Acceptance criteria mapping (issue #70)
---------------------------------------
- run_morning_briefing_job()       — entry point
- _is_within_15_min                — wrap-midnight aware
- already_sent_today               — events-table query
- send + inline keyboard           — Notifier.send_message
- track event with level           — analytics.atrack
- rate limit                       — asyncio.sleep(1) per user
- error per user does not crash    — try/except inside loop
- timezone Asia/Ho_Chi_Minh        — tz used for both window and dedup
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.briefing_formatter import BriefingFormatter
from backend.bot.keyboards.briefing_keyboard import briefing_actions_keyboard
from backend.database import get_session_factory
from backend.models.event import Event
from backend.models.expense import Expense
from backend.models.user import User
from backend.ports.notifier import get_notifier

logger = logging.getLogger(__name__)

WINDOW_MINUTES = 15
INTER_USER_DELAY_SECONDS = 1.0
ACTIVE_WINDOW_DAYS = 30
BRIEFING_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def _is_within_15_min(now: time, target: time) -> bool:
    """True iff ``now`` is in ``[target, target + 15min)``.

    Handles wrap-around midnight: if ``target`` is 23:55, the window
    extends to 00:10 — a ``now`` of 00:05 is inside it.
    """
    now_min = now.hour * 60 + now.minute
    target_min = target.hour * 60 + target.minute
    delta = (now_min - target_min) % (24 * 60)
    return delta < WINDOW_MINUTES


async def already_sent_today(
    db: AsyncSession,
    user_id,
    *,
    tz: ZoneInfo = BRIEFING_TIMEZONE,
    now: datetime | None = None,
) -> bool:
    """Did we already send a briefing in the user's local "today"?

    Local-day boundary (rather than UTC) so a 23:50 send doesn't dedup
    against a 00:10 send 20 minutes later that's actually tomorrow's
    briefing for an early-bird user.
    """
    now = now or datetime.now(tz)
    local_midnight = datetime.combine(now.date(), time(0, 0), tzinfo=tz)
    cutoff_utc = local_midnight.astimezone(timezone.utc)

    stmt = select(Event.id).where(
        Event.user_id == user_id,
        Event.event_type == analytics.EventType.MORNING_BRIEFING_SENT,
        Event.timestamp >= cutoff_utc,
    ).limit(1)
    return (await db.execute(stmt)).first() is not None


async def _get_briefing_candidates(db: AsyncSession) -> list[User]:
    """Active, briefing-enabled users that we'd consider sending to.

    Active = at least one non-deleted expense in the last 30 days.
    Mirrors ``backend.jobs._active_users.get_active_users`` but with
    extra ``briefing_enabled`` and ``telegram_id`` predicates.
    """
    since = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WINDOW_DAYS)
    active_ids_stmt = select(distinct(Expense.user_id)).where(
        Expense.created_at >= since,
        Expense.deleted_at.is_(None),
    )
    user_ids = [r[0] for r in (await db.execute(active_ids_stmt)).all()]
    if not user_ids:
        return []

    stmt = select(User).where(
        User.id.in_(user_ids),
        User.is_active.is_(True),
        User.deleted_at.is_(None),
        User.telegram_id.isnot(None),
        User.briefing_enabled.is_(True),
    )
    return list((await db.execute(stmt)).scalars())


async def run_morning_briefing_job(
    *,
    now: datetime | None = None,
) -> int:
    """Send pending briefings; return the number sent.

    ``now`` is injectable for tests — production calls pass nothing
    and we read the wall clock in Asia/Ho_Chi_Minh.
    """
    now = now or datetime.now(BRIEFING_TIMEZONE)
    formatter = BriefingFormatter()
    notifier = get_notifier()
    sent = 0
    skipped_window = 0
    skipped_dedup = 0
    failed = 0

    session_factory = get_session_factory()
    async with session_factory() as db:
        candidates = await _get_briefing_candidates(db)

    logger.info(
        "morning-briefing: scanning %d candidates at %s",
        len(candidates), now.isoformat(),
    )

    for user in candidates:
        target = user.briefing_time or time(7, 0)
        if not _is_within_15_min(now.time(), target):
            skipped_window += 1
            continue

        try:
            async with session_factory() as db:
                if await already_sent_today(db, user.id, now=now):
                    skipped_dedup += 1
                    continue

                result = await formatter.generate_for_user(db, user)

            send_response = await notifier.send_message(
                chat_id=user.telegram_id,
                text=result.text,
                reply_markup=briefing_actions_keyboard(),
            )
            # Notifier returns ``None`` on adapter error (it logs but
            # doesn't raise — that's the contract). Treat as failure
            # so the dedup row isn't written and we'll retry next run.
            if send_response is None:
                failed += 1
                logger.warning(
                    "morning-briefing: send failed for user=%s — will retry",
                    user.id,
                )
                continue

            await analytics.atrack(
                analytics.EventType.MORNING_BRIEFING_SENT,
                user_id=user.id,
                properties={
                    "level": result.level.value,
                    "is_empty_state": result.is_empty_state,
                    "char_count": result.char_count,
                },
            )
            sent += 1

        except Exception:
            failed += 1
            logger.exception(
                "morning-briefing: user %s failed — continuing", user.id,
            )

        # Rate limit — Telegram tolerates ~30 msg/sec but we stay
        # under 1/sec to leave headroom for the empathy + milestone
        # jobs that can run in the same minute.
        await asyncio.sleep(INTER_USER_DELAY_SECONDS)

    logger.info(
        "morning-briefing: done — sent=%d skipped_window=%d "
        "skipped_dedup=%d failed=%d",
        sent, skipped_window, skipped_dedup, failed,
    )
    return sent


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_morning_briefing_job())
