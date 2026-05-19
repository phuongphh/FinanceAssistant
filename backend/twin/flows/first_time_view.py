"""First-time Twin story flow orchestration for Phase 4.3 Epic 2."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.twin_view_event import TwinViewEvent
from backend.twin.views import (
    narrative_screen_action,
    narrative_screen_causality,
    narrative_screen_chart,
    narrative_screen_intro,
    narrative_screen_scenarios,
)

RESHOW_AFTER_DAYS = 30
_FULL_EVENTS = {"story_completed", "story_skipped"}


async def should_show_full_story(db: AsyncSession, user_id: uuid.UUID) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RESHOW_AFTER_DAYS)
    result = await db.execute(
        select(TwinViewEvent)
        .where(TwinViewEvent.user_id == user_id, TwinViewEvent.event_type.in_(_FULL_EVENTS))
        .order_by(desc(TwinViewEvent.created_at))
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last is None:
        return True
    created_at = last.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at < cutoff


async def mark_story_completed(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    surface: str,
    flow_mode: str = "compact",
    screen_id: str | None = None,
) -> None:
    """Record a ``story_completed`` event for the reshow gate.

    Logging this from the Telegram preamble path keeps
    ``should_show_full_story`` consistent between Mini App and Bot
    surfaces — both feed the same 30-day cooldown.
    """
    db.add(
        TwinViewEvent(
            user_id=user_id,
            event_type="story_completed",
            screen_id=screen_id,
            flow_mode=flow_mode,
            metadata_={"surface": surface},
        )
    )
    await db.flush()


def build_story_flow(data: dict[str, Any], *, full_flow: bool) -> dict[str, Any]:
    screens = [
        narrative_screen_intro.build(data),
        narrative_screen_scenarios.build(data),
        narrative_screen_causality.build(data),
        narrative_screen_action.build(data),
        narrative_screen_chart.build(data),
    ]
    if not full_flow:
        screens = [
            {**screens[1], "title": "Tóm tắt 3 phiên bản Bé Tiền"},
            {**screens[4], "title": "Chi tiết kỹ thuật khi cần"},
        ]
    return {
        "mode": "full" if full_flow else "compact",
        "reshow_after_days": RESHOW_AFTER_DAYS,
        "skip_label": "Bỏ qua, xem nhanh",
        "screens": screens,
    }
