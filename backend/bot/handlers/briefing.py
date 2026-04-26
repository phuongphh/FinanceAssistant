"""Inline-keyboard handlers for morning-briefing button taps.

Four buttons live on every briefing (see
``backend/bot/keyboards/briefing_keyboard.py``):

    briefing:dashboard   — open the wealth dashboard (Mini App in P3A-21)
    briefing:story       — start storytelling expense capture
    briefing:add_asset   — open the asset-add wizard
    briefing:settings    — change briefing time / opt out

The handler's job is small:

1. Track the funnel events (``MORNING_BRIEFING_OPENED`` once, then the
   specific ``BRIEFING_*_CLICKED`` for the action).
2. Hand off to the underlying feature handler when one exists, or
   send a friendly placeholder so the button doesn't feel broken.

``add_asset`` forwards into the existing asset-entry wizard so the
flow is unchanged from the user's perspective — only the analytics
attribution is new.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.keyboards.briefing_keyboard import (
    BRIEFING_ACTION_ADD_ASSET,
    BRIEFING_ACTION_DASHBOARD,
    BRIEFING_ACTION_SETTINGS,
    BRIEFING_ACTION_STORY,
    CB_BRIEFING,
)
from backend.bot.keyboards.common import parse_callback
from backend.models.event import Event
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import answer_callback, send_message

logger = logging.getLogger(__name__)

# Same window as `analytics.BRIEFING_OPEN_WINDOW_SECONDS`. Inlined as
# a timedelta to keep the dedup query readable.
_OPEN_WINDOW = timedelta(minutes=30)

_ACTION_TO_EVENT = {
    BRIEFING_ACTION_DASHBOARD: analytics.EventType.BRIEFING_DASHBOARD_CLICKED,
    BRIEFING_ACTION_STORY: analytics.EventType.BRIEFING_STORY_CLICKED,
    BRIEFING_ACTION_ADD_ASSET: analytics.EventType.BRIEFING_ADD_ASSET_CLICKED,
    BRIEFING_ACTION_SETTINGS: analytics.EventType.BRIEFING_SETTINGS_CLICKED,
}

# User-facing text per action — kept short, follows tone guide. The
# ``add_asset`` and ``story`` actions do NOT live here because they
# forward into real handlers rather than showing a placeholder.
_ACTION_PLACEHOLDER = {
    BRIEFING_ACTION_DASHBOARD: (
        "📊 Dashboard sắp ra mắt — mình đang hoàn thiện ở "
        "P3A-21. Tạm thời gõ /baocao để xem báo cáo nhé."
    ),
    BRIEFING_ACTION_SETTINGS: (
        "⚙️ Mặc định mình gửi briefing lúc 7:00. "
        "Tính năng đổi giờ sẽ có ở bản tới."
    ),
}


async def _record_open_if_first(
    db: AsyncSession, user_id, *, now: datetime | None = None,
) -> None:
    """Fire ``MORNING_BRIEFING_OPENED`` at most once per briefing.

    A brief is "opened" the first time the user taps any button within
    ``_OPEN_WINDOW`` of the most recent send. Subsequent taps still
    record their action-specific click event but skip this one — we
    don't want a flurry of button-tapping to inflate the open count.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - _OPEN_WINDOW

    last_sent_stmt = (
        select(Event.timestamp)
        .where(
            Event.user_id == user_id,
            Event.event_type == analytics.EventType.MORNING_BRIEFING_SENT,
            Event.timestamp >= cutoff,
        )
        .order_by(Event.timestamp.desc())
        .limit(1)
    )
    last_sent = (await db.execute(last_sent_stmt)).scalar_one_or_none()
    if last_sent is None:
        # No briefing in the open window — must be a stale message
        # tap, don't credit an open.
        return

    already_opened_stmt = (
        select(Event.id)
        .where(
            Event.user_id == user_id,
            Event.event_type == analytics.EventType.MORNING_BRIEFING_OPENED,
            Event.timestamp >= last_sent,
        )
        .limit(1)
    )
    if (await db.execute(already_opened_stmt)).first() is not None:
        return

    await analytics.atrack(
        analytics.EventType.MORNING_BRIEFING_OPENED,
        user_id=user_id,
    )


async def handle_briefing_callback(
    db: AsyncSession, callback_query: dict,
) -> bool:
    """Route any ``briefing:*`` callback. Returns True if handled."""
    data: str = callback_query.get("data") or ""
    if not data.startswith(f"{CB_BRIEFING}:"):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    telegram_id = (callback_query.get("from") or {}).get("id")

    if chat_id is None or telegram_id is None:
        await answer_callback(callback_id)
        return True

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(
            callback_id,
            text="Chưa thấy bạn — gõ /start để mình chào nhé 🌱",
            show_alert=True,
        )
        return True

    _, parts = parse_callback(data)
    action = parts[0] if parts else ""

    await answer_callback(callback_id)
    await _record_open_if_first(db, user.id)

    event_type = _ACTION_TO_EVENT.get(action)
    if event_type:
        analytics.track(event_type, user_id=user.id)

    if action == BRIEFING_ACTION_ADD_ASSET:
        # Forward into the asset wizard. Local import so a circular
        # dependency between briefing handler and asset_entry handler
        # never bites — both modules import from each other's
        # neighbours otherwise.
        from backend.bot.handlers.asset_entry import start_asset_wizard
        await start_asset_wizard(db, chat_id, user)
        return True

    if action == BRIEFING_ACTION_STORY:
        # Forward into storytelling, tagging the source as "from
        # briefing" so the analytics funnel can separate
        # ``storytelling_from_briefing`` (intentional retention path)
        # from ``storytelling_direct`` (power-user typed /story).
        # Local import to mirror the asset-entry pattern above.
        from backend.bot.handlers.storytelling import (
            SOURCE_FROM_BRIEFING,
            start_storytelling,
        )
        await start_storytelling(db, chat_id, user, source=SOURCE_FROM_BRIEFING)
        return True

    placeholder = _ACTION_PLACEHOLDER.get(action)
    if placeholder:
        await send_message(chat_id=chat_id, text=placeholder)
    else:
        logger.warning(
            "briefing-callback: unknown action %r (data=%s)", action, data
        )

    return True
