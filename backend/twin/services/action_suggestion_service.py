from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.event import Event

_CONTENT_PATH = Path(__file__).resolve().parents[3] / "content" / "twin" / "action_suggestion.yaml"


@dataclass(frozen=True, slots=True)
class ActionSuggestion:
    type: str
    title: str
    description: str
    time_estimate_minutes: int
    deep_link: str
    buttons: tuple[dict[str, str], ...]


@lru_cache(maxsize=1)
def _library() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _direction(delta_pct: float | int | str) -> str:
    value = float(delta_pct)
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "stable"


async def _dismissed_types(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(Event)
        .where(Event.user_id == user_id, Event.event_type == "action_suggestion.dismissed", Event.timestamp >= cutoff)
        .order_by(desc(Event.timestamp))
        .limit(50)
    )
    counts: dict[str, int] = {}
    for event in result.scalars().all():
        typ = (event.properties or {}).get("suggestion_type")
        if typ:
            counts[typ] = counts.get(typ, 0) + 1
    return {typ for typ, count in counts.items() if count >= 3}


async def suggest_action(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    state_segment: str = "mass_affluent",
    delta_pct: float | int | str = 0,
    has_goal: bool = False,
) -> ActionSuggestion:
    direction = _direction(delta_pct)
    suppressed = await _dismissed_types(db, user_id)
    suggestions = _library().get("suggestions", [])
    fallback = _library()["fallback"]
    candidates = [
        s for s in suggestions
        if s.get("state_segment") in {state_segment, "default"}
        and s.get("delta_direction") == direction
        and bool(s.get("has_goal")) == bool(has_goal)
        and s.get("type") not in suppressed
    ]
    selected = candidates[0] if candidates else fallback
    return ActionSuggestion(
        type=str(selected.get("type", "fallback")),
        title=selected["title"],
        description=selected["description"],
        time_estimate_minutes=int(selected.get("time_estimate_minutes", 5)),
        deep_link=selected["deep_link"],
        buttons=(
            {"text": "Làm ngay", "url": selected["deep_link"]},
            {"text": "Để sau", "callback_data": f"action_suggestion:dismiss:{selected.get('type', 'fallback')}"},
        ),
    )


def render_action_card(suggestion: ActionSuggestion) -> str:
    return "\n".join([
        f"🎯 {suggestion.title}",
        suggestion.description,
        f"⏱️ Khoảng {suggestion.time_estimate_minutes} phút",
    ])


async def log_action_event(db: AsyncSession, user_id: uuid.UUID, event_type: str, suggestion: ActionSuggestion) -> None:
    db.add(Event(user_id=user_id, event_type=event_type, properties={"suggestion_type": suggestion.type, "deep_link": suggestion.deep_link}))
    await db.flush()
