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
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.analytics import EventType
from backend.bot.formatters.tone import resolve_tone
from backend.bot.personality import empathy_engine
from backend.database import get_session_factory
from backend.intent.handlers.decision_flags import (
    is_activation_nudge_enabled,
    is_drift_warning_enabled,
    is_tone_dial_enabled,
)
from backend.jobs._active_users import get_active_users
from backend.models.event import Event
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


# Phase 4.4 Epic 3 — the proactive-companion trigger
# (``onboarding_no_twin_return``) is gated here, at the job edge, NOT in
# the engine/service (layer contract: services never read env). Off →
# the engine skips the new trigger but every pre-existing empathy trigger
# still fires.
def _proactive_companion_enabled() -> bool:
    return os.environ.get("PROACTIVE_COMPANION_ENABLED", "true").lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


async def _get_activation_candidates(
    db: AsyncSession, *, now: datetime
) -> list[User]:
    """Users who opened the bot recently but never activated.

    The ``never_activated`` trigger targets the "0 tin nhắn" cohort — users
    with a ``bot_started`` event who never logged an expense, so they're
    invisible to ``get_active_users``. We pull anyone who opened the bot
    inside the trigger's window and hasn't finished onboarding; the engine's
    own window / activation / cooldown checks decide whether the nudge
    actually fires.

    Bounded to the trigger's window (``ACTIVATION_NUDGE_MAX_DAYS``) via the
    ``bot_started`` timestamp so we never scan the whole table.
    """
    since = now - timedelta(days=empathy_engine.ACTIVATION_NUDGE_MAX_DAYS)
    started_user_ids = (
        select(Event.user_id)
        .where(
            Event.event_type == EventType.BOT_STARTED,
            Event.timestamp >= since,
            Event.user_id.isnot(None),
        )
        .distinct()
    )
    stmt = select(User).where(
        User.id.in_(started_user_ids),
        User.onboarding_completed_at.is_(None),
        User.deleted_at.is_(None),
        User.is_active.is_(True),
        User.telegram_id.isnot(None),
    )
    return list((await db.execute(stmt)).scalars())


async def _get_onboarded_candidates(
    db: AsyncSession, *, now: datetime
) -> list[User]:
    """Recently-onboarded users who may need the proactive nudge.

    ``get_active_users`` keys off having a non-deleted expense, so a user
    who finished onboarding (saw their Twin once) but has not logged a
    single expense never enters that set — yet that drifted-after-WOW
    cohort is *exactly* who the ``onboarding_no_twin_return`` trigger
    targets. We pull them in separately here, gated by the proactive flag
    at the caller, and the engine's own window/cooldown checks still
    decide whether the trigger actually fires.

    Bounded to the trigger's activation window
    (``ONBOARDING_SILENCE_MAX_DAYS``) so we never scan the whole table.
    """
    since = now - timedelta(days=empathy_engine.ONBOARDING_SILENCE_MAX_DAYS)
    stmt = select(User).where(
        User.onboarding_completed_at.isnot(None),
        User.onboarding_completed_at >= since,
        User.deleted_at.is_(None),
        User.is_active.is_(True),
        User.telegram_id.isnot(None),
    )
    return list((await db.execute(stmt)).scalars())


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

    proactive_on = _proactive_companion_enabled()
    activation_on = is_activation_nudge_enabled()

    session_factory = get_session_factory()
    async with session_factory() as db:
        users = await get_active_users(db, days=ACTIVE_WINDOW_DAYS)
        # Fold in users who are invisible to get_active_users (no expense
        # yet) but are the target of a proactive trigger:
        #   - proactive companion → recently-onboarded, drifted-after-WOW.
        #   - activation nudge → opened the bot but never activated.
        if proactive_on or activation_on:
            by_id = {u.id: u for u in users}
            if proactive_on:
                for u in await _get_onboarded_candidates(db, now=now_utc):
                    by_id.setdefault(u.id, u)
            if activation_on:
                for u in await _get_activation_candidates(db, now=now_utc):
                    by_id.setdefault(u.id, u)
            users = list(by_id.values())

    logger.info("empathy-check: scanning %d candidate users", len(users))

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

        trigger = await empathy_engine.check_all_triggers(
            db,
            user,
            now=now,
            include_proactive=_proactive_companion_enabled(),
            include_activation_nudge=is_activation_nudge_enabled(),
            include_drift=is_drift_warning_enabled(),
        )
        if not trigger:
            return

        # Tone dial read at the job edge (layer contract); dark → tone=None →
        # render_message keeps the legacy empathy copy.
        tone = resolve_tone(user.tone_preference) if is_tone_dial_enabled() else None
        message = empathy_engine.render_message(trigger, user, tone=tone)
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

        # The activation nudge feeds a dedicated funnel (E2 #2.2:
        # first-message-fired vs user-first-reply); everything else stays on
        # the generic EMPATHY_SENT stream so the two don't co-mingle.
        sent_event = (
            EventType.ACTIVATION_NUDGE_SENT
            if trigger.name == "never_activated"
            else EventType.EMPATHY_SENT
        )
        analytics.track(
            sent_event,
            user_id=user.id,
            properties={"trigger": trigger.name},
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_hourly_empathy_check())
