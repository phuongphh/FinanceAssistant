"""LLM narrative for life events — Phase 4B Epic 2 (S12).

Tone rules (hard constraints):
  - Never suggest delaying marriage / having children for financial reasons.
  - No alarming words: "cảnh báo", "nguy hiểm", "thất bại", "rủi ro cao".
  - Always frame impact as "trade-off bình thường" or "có thể plan được".
  - End with a concrete suggested action (from the preset's
    ``suggested_action`` field).

Failure mode:
  Returns the YAML ``fallback`` template if the LLM call fails or returns
  an obviously off-tone response (length / forbidden words check). Keeps
  the UX warm even when external dependencies hiccup.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
from backend.models.life_event import LifeEvent, LifeEventType
from backend.models.user import User
from backend.services.llm_service import LLMError, call_llm

logger = logging.getLogger(__name__)

_COPY_PATH = Path(__file__).resolve().parents[2] / "content" / "life_events.yaml"

# Substrings that violate the persona — if any appear in the LLM output we
# discard the response and use the YAML fallback. Lowercased for matching.
_FORBIDDEN_PHRASES = (
    "cảnh báo",
    "nguy hiểm",
    "thất bại tài chính",
    "rủi ro cao",
    "trì hoãn kết hôn",
    "trì hoãn cưới",
    "hoãn cưới",
    "trì hoãn sinh con",
    "đừng sinh",
    "không nên cưới",
    "không nên sinh",
    "khoan cưới",
)

_MIN_LEN = 80
_MAX_LEN = 320


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _event_label(event: LifeEvent) -> str:
    meta = _copy()["presets"].get(event.event_type, {})
    icon = meta.get("icon", "")
    base = event.title or meta.get("label", event.event_type)
    return f"{icon} {base}".strip()


def _suggested_action(event: LifeEvent) -> str:
    meta = _copy()["presets"].get(event.event_type, {})
    return meta.get("suggested_action", "Tăng tiết kiệm đều mỗi tháng.")


def _format_delta(delta: Decimal) -> str:
    if delta == 0:
        return _copy()["narrative"]["empty_impact"]
    amount = format_money_short(abs(delta))
    template_key = "delta_positive" if delta > 0 else "delta_negative"
    return _copy()["narrative"][template_key].format(amount=amount)


def _is_clean(text: str) -> bool:
    lowered = text.lower()
    return not any(phrase in lowered for phrase in _FORBIDDEN_PHRASES)


async def build_life_event_narrative(
    db: AsyncSession,
    user: User,
    event: LifeEvent,
    *,
    p50_delta: Decimal,
    target_year: int,
    wealth_level: str,
) -> str:
    """Return 3-4 sentence Vietnamese narrative for the life-event impact view."""
    copy = _copy()["narrative"]
    event_label = _event_label(event)
    fallback = copy["fallback"].format(event_label=event_label)
    if not event.planned_date:
        return fallback

    prompt = copy["prompt"].format(
        event_label=event_label,
        year=event.planned_date.year,
        target_year=target_year,
        p50_delta=_format_delta(p50_delta),
        wealth_level=wealth_level or "chưa xác định",
        suggested_action=_suggested_action(event),
    )

    try:
        text = await call_llm(
            prompt,
            task_type="life_event_narrative",
            db=db,
            user_id=user.id,
            use_cache=True,
            cache_ttl_days=14,
        )
    except (LLMError, Exception):
        logger.warning("life-event narrative LLM call failed user=%s", user.id)
        return fallback

    cleaned = " ".join(text.replace("*", "").replace("_", "").split())
    if len(cleaned) < _MIN_LEN or len(cleaned) > _MAX_LEN:
        return fallback
    if not _is_clean(cleaned):
        logger.warning(
            "life-event narrative rejected for persona violation user=%s", user.id
        )
        return fallback
    return cleaned


def event_type_or_custom(value: str) -> LifeEventType:
    try:
        return LifeEventType(value)
    except ValueError:
        return LifeEventType.CUSTOM


def summary_for_twin_narrative(events: list[LifeEvent]) -> str:
    """Compact one-line summary of active events for the Twin prompt.

    Phase 4A's twin_narrative_service.py prompt has a ``life_events_summary``
    field that took "không có" as a placeholder. With Epic 2 done we can
    feed it real data: "Mua nhà 2028, Con đầu lòng 2030".
    """
    if not events:
        return "không có"
    parts = []
    for event in events[:3]:  # cap so the prompt stays compact
        meta = _copy()["presets"].get(event.event_type, {})
        label = event.title or meta.get("short_label", event.event_type)
        year = event.planned_date.year if event.planned_date else "?"
        parts.append(f"{label} {year}")
    if len(events) > 3:
        parts.append(f"… (+{len(events) - 3})")
    return ", ".join(parts)
