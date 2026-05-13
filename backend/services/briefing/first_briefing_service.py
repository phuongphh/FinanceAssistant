"""First-morning-briefing decorator (Phase 4.1, Story A.8).

Wraps the normal briefing payload with an explainer + "what is this?"
inline button the first time a user receives a morning briefing.

Detection: count rows of ``Event`` where ``event_type=MORNING_BRIEFING_SENT``
for the user — if zero, this is the first briefing. The check runs
BEFORE the new row is written (caller orders the call right).

Logic is intentionally simple: no smart timing, no notification
preference inspection. The first briefing fires on the standard 8h
cron whatever day comes after onboarding completion — if user muted
the chat, the briefing still lands and they see it on their next
visit. (See phase-4.1-detailed.md §A.8 for the design rationale.)
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.models.event import Event

logger = logging.getLogger(__name__)


_COPY_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "onboarding"
    / "first_briefing.yaml"
)


def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


async def is_first_briefing(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """True iff user has zero ``MORNING_BRIEFING_SENT`` events recorded.

    Cheap query (indexed on user_id + event_type by the existing
    ``idx_events_user_type_date``). Caller must invoke BEFORE writing
    the new event row for this run.
    """
    count = (
        await db.execute(
            select(func.count(Event.id)).where(
                Event.user_id == user_id,
                Event.event_type == analytics.EventType.MORNING_BRIEFING_SENT,
            )
        )
    ).scalar()
    return (count or 0) == 0


def decorate(text: str) -> tuple[str, dict]:
    """Prepend the first-briefing explainer + attach inline keyboard.

    Returns ``(decorated_text, reply_markup)`` — caller passes both to
    Notifier.send_message in place of the plain briefing text and the
    default briefing keyboard.
    """
    copy = _copy()
    decorated = f"{copy['explainer']}\n\n{text}"
    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": copy["explain_button"]["label"],
                    "callback_data": copy["explain_button"]["callback"],
                }
            ]
        ]
    }
    return decorated, reply_markup


def explanation_text() -> str:
    """Long-form explainer shown when user taps the inline button."""
    return _copy()["explanation"]
