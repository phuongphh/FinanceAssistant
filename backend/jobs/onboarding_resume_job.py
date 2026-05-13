"""Onboarding resume nudge worker (Phase 4.1, Story A.2).

Runs every 5 minutes. Finds users stuck on an onboarding step for >10
minutes who haven't received a nudge yet, sends one warm message
with two CTAs (continue / use demo), and marks ``nudge_sent_at`` so
they NEVER get a second nudge — anti-spam is a hard cap, not a
backoff.

Dispatches via the Notifier port so multi-channel (Telegram + Zalo)
fans out automatically when Phase 5.x activates Zalo.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml

from backend import analytics
from backend.database import get_session_factory
from backend.models.onboarding_session import (
    OnboardingSession,
    STEP_FIRST_ASSET,
    STEP_GOAL_QUESTION,
    STEP_TWIN_SHOWN,
)
from backend.models.user import User
from backend.services.notifier_resolver import resolve_targets
from backend.services.onboarding import onboarding_service

logger = logging.getLogger(__name__)


_NUDGE_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "onboarding" / "resume_nudge.yaml"
)

# Inter-user delay so a burst of nudges doesn't trip the bot's rate
# limit (Telegram caps at ~30 msg/sec; we batch under that comfortably).
INTER_USER_DELAY_SECONDS = 0.5
STUCK_MINUTES = 10


def _load_copy() -> dict[str, Any]:
    with open(_NUDGE_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _build_message(session: OnboardingSession) -> tuple[str, dict]:
    """Render nudge text + inline keyboard for a stuck session."""
    copy = _load_copy()
    step_labels: dict[str, str] = copy["step_labels"]
    label = step_labels.get(session.current_step, session.current_step)
    text = copy["nudge"].format(step_label=label)
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": copy["buttons"]["continue"],
                    "callback_data": copy["continue_callback"],
                },
                {
                    "text": copy["buttons"]["demo"],
                    "callback_data": copy["demo_callback"],
                },
            ]
        ]
    }
    return text, keyboard


async def _send_nudge(session: OnboardingSession, user: User) -> bool:
    """Dispatch the nudge to every channel the user has opted into.

    Returns True if at least one channel accepted the message.
    """
    try:
        text, reply_markup = _build_message(session)
        targets = resolve_targets(user)
        if not targets:
            return False
        sent = False
        for target in targets:
            try:
                # Telegram chat_id is the user's telegram_id; Zalo uses
                # zalo_user_id stringified — Notifier.send_message
                # accepts an int for Telegram, str via kwargs for Zalo.
                if target.channel == "telegram":
                    await target.notifier.send_message(
                        chat_id=int(target.target_id),
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                else:
                    # Zalo does not support inline keyboards; degrade
                    # gracefully by sending text only.
                    await target.notifier.send_message(
                        chat_id=target.target_id,
                        text=text,
                    )
                sent = True
            except Exception:
                logger.exception(
                    "resume_nudge: send failed user=%s channel=%s",
                    user.id,
                    target.channel,
                )
        return sent
    except Exception:
        logger.exception("resume_nudge: render failed user=%s", user.id)
        return False


async def run_onboarding_resume_job() -> int:
    """Entry point for the APScheduler cron. Returns # nudges sent."""
    session_factory = get_session_factory()
    sent_count = 0
    async with session_factory() as db:
        try:
            stuck = await onboarding_service.find_stuck_sessions(
                db, stuck_minutes=STUCK_MINUTES
            )
            if not stuck:
                return 0

            # Filter to only valid resumable steps. (twin_shown means
            # they got the chart — let them be, the feedback prompt is
            # optional.)
            stuck = [
                s
                for s in stuck
                if s.current_step
                in (STEP_GOAL_QUESTION, STEP_FIRST_ASSET, STEP_TWIN_SHOWN)
            ]

            for session in stuck:
                user = await db.get(User, session.user_id)
                if not user:
                    continue
                ok = await _send_nudge(session, user)
                if ok:
                    await onboarding_service.mark_nudge_sent(db, session.user_id)
                    analytics.track(
                        "onboarding_v2_resume_nudge_sent",
                        user_id=session.user_id,
                        properties={"stuck_step": session.current_step},
                    )
                    sent_count += 1
                # Best-effort rate limit between users.
                await asyncio.sleep(INTER_USER_DELAY_SECONDS)

            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Onboarding resume job failed")
            raise

    if sent_count:
        logger.info("Sent %d onboarding resume nudges", sent_count)
    return sent_count
