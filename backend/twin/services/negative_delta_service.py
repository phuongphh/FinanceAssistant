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
from backend.twin.services.action_suggestion_service import ActionSuggestion, render_action_card
from backend.twin.services.causality_service import CausalityBreakdown

_CONTENT_PATH = Path(__file__).resolve().parents[3] / "content" / "twin" / "negative_delta_copy.yaml"


@dataclass(frozen=True, slots=True)
class NegativeDeltaMessage:
    text: str
    visual_cue: str
    should_notify: bool
    skip_reason: str | None = None


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_respectful_copy(text: str) -> bool:
    lowered = text.lower()
    return not any(word.lower() in lowered for word in _copy().get("forbidden_words", []))


async def can_notify_negative(db: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=int(_copy().get("frequency_cap_days", 7)))
    result = await db.execute(
        select(func.count()).select_from(Event).where(
            Event.user_id == user_id,
            Event.event_type == "twin.negative_delta_notified",
            Event.timestamp >= cutoff,
        )
    )
    return int(result.scalar_one() or 0) == 0


def build_negative_delta_message(breakdown: CausalityBreakdown, suggestion: ActionSuggestion) -> NegativeDeltaMessage:
    factor = breakdown.factors[0].factor if breakdown.factors else "một biến động tài chính trong tuần"
    copy = _copy()
    headline = copy["headline_variants"][0]
    body = copy["body_variants"][0].format(factor=factor)
    text = f"{headline}\n{body}\n\n{render_action_card(suggestion)}"
    return NegativeDeltaMessage(text=text, visual_cue="🌧️ Twin Mưa Cuối Tuần", should_notify=validate_respectful_copy(text))


async def log_negative_notification(db: AsyncSession, user_id: uuid.UUID, factor: str) -> None:
    db.add(Event(user_id=user_id, event_type="twin.negative_delta_notified", properties={"factor": factor}))
    await db.flush()
