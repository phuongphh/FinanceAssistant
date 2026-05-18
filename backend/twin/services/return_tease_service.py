from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.event import Event

_CONTENT_PATH = Path(__file__).resolve().parents[3] / "content" / "twin" / "return_tease.yaml"


@dataclass(frozen=True, slots=True)
class ReturnTease:
    confirmation: str
    tease: str | None
    briefing_tag: str
    send_at: datetime


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def next_briefing_time(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    base = now.astimezone(timezone.utc)
    target = base.replace(hour=1, minute=0, second=0, microsecond=0)  # 08:00 ICT
    if base.hour >= 16:  # 23:00+ ICT: same coming morning
        return target + timedelta(days=1)
    if base >= target:
        return target + timedelta(days=1)
    return target


async def completed_actions_this_week(db: AsyncSession, user_id: uuid.UUID) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(func.count()).select_from(Event).where(
            Event.user_id == user_id,
            Event.event_type == "action_suggestion.complete",
            Event.timestamp >= cutoff,
        )
    )
    return int(result.scalar_one() or 0)


async def build_return_tease(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    action_title: str,
    now: datetime | None = None,
) -> ReturnTease:
    copy = _copy()
    count = await completed_actions_this_week(db, user_id)
    variant_index = count % len(copy["confirmation_variants"])
    tease = None if count >= 3 and count % 2 == 1 else copy["tease_variants"][count % len(copy["tease_variants"])]
    return ReturnTease(
        confirmation=copy["confirmation_variants"][variant_index],
        tease=tease,
        briefing_tag="twin_check_back_in",
        send_at=next_briefing_time(now),
    )


async def record_action_completed(db: AsyncSession, user_id: uuid.UUID, *, action_title: str) -> ReturnTease:
    tease = await build_return_tease(db, user_id, action_title=action_title)
    db.add(Event(user_id=user_id, event_type="action_suggestion.complete", properties={"action_title": action_title, "briefing_tag": tease.briefing_tag, "send_at": tease.send_at.isoformat()}))
    await db.flush()
    return tease


async def briefing_prefix_for_user(db: AsyncSession, user_id: uuid.UUID) -> str | None:
    result = await db.execute(
        select(Event).where(Event.user_id == user_id, Event.event_type == "action_suggestion.complete").order_by(Event.timestamp.desc()).limit(1)
    )
    event = result.scalar_one_or_none()
    if event is None:
        return None
    title = (event.properties or {}).get("action_title", "một việc nhỏ")
    return _copy()["briefing_prefix"].format(action=title)
