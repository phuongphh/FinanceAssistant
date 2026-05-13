"""Life-event impact chart — orchestrates data fetch + matplotlib render.

The matplotlib call lives in ``backend/adapters/chart_renderer.py`` (transport
layer). This module owns the domain logic: figure out which cones to diff,
which milestone years to annotate, and how to format the labels.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.chart_renderer import render_life_event_impact_chart as _render_png
from backend.bot.formatters.money import format_money_short
from backend.life_events.impact import (
    adjust_cone_with_events,
    base_year_from_computed_at,
)
from backend.models.life_event import LifeEvent
from backend.twin.services.twin_projection_service import SCENARIO_CURRENT
from backend.twin.services.twin_query_service import get_latest_projection

logger = logging.getLogger(__name__)

_MILESTONE_OFFSETS_FALLBACK = (1, 5, 10)  # short / mid / long horizon
_PHASE_MILESTONE_YEARS = (2027, 2030, 2035)

_COPY_PATH = Path(__file__).resolve().parents[2] / "content" / "life_events.yaml"


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def render_life_event_impact_chart(
    db: AsyncSession,
    user_id: uuid.UUID,
    event: LifeEvent,
) -> bytes | None:
    """Render the before/after PNG for one event. Returns ``None`` if no data.

    Uses ``cone_data`` (with all events) for the "after" view and
    ``base_cone_data`` (no events) for the "before" view, then re-applies
    any OTHER active events to the before view so the diff isolates just
    THIS event's impact — not the cumulative impact of everything in the
    user's plan.
    """
    projection = await get_latest_projection(db, user_id, scenario=SCENARIO_CURRENT)
    if projection is None or not projection.cone_data:
        return None

    after_cone = list(projection.cone_data)
    base_cone = list(projection.base_cone_data or projection.cone_data)
    base_year = base_year_from_computed_at(projection.computed_at)

    # Re-apply every OTHER active event to the base cone, so the "before" view
    # represents "world without THIS event but with all the user's other plans".
    from backend.life_events import service as life_event_service

    other_events = [
        ev
        for ev in await life_event_service.list_for_user(db, user_id)
        if ev.id != event.id
    ]
    before_cone = adjust_cone_with_events(base_cone, other_events, base_year)

    impact_labels = _build_impact_labels(before_cone, after_cone, base_year)
    title = _chart_title(event)
    try:
        return _render_png(
            before_cone=before_cone,
            after_cone=after_cone,
            base_year=base_year,
            title=title,
            impact_labels=impact_labels,
        )
    except Exception:
        logger.exception(
            "life-event impact chart render failed user=%s event=%s",
            user_id,
            event.id,
        )
        return None


def _chart_title(event: LifeEvent) -> str:
    """Localized chart title using event.title (falls back to preset label)."""
    title = event.title
    if not title:
        meta = _copy().get("presets", {}).get(event.event_type, {})
        title = meta.get("label", event.event_type)
    return _copy()["chart"]["title"].format(title=title)


def _build_impact_labels(
    before_cone: list[dict],
    after_cone: list[dict],
    base_year: int,
) -> list[tuple[int, str]]:
    """Annotate the chart at canonical milestone years (or first/mid/last)."""
    labels: list[tuple[int, str]] = []
    horizon = max(int(p.get("year", 0)) for p in before_cone) if before_cone else 0

    # Prefer the absolute calendar years from the phase plan (2027 / 2030 / 2035)
    # when they fall within the horizon — they're shared across Twin surfaces.
    candidate_year_idxs: list[int] = []
    for cal_year in _PHASE_MILESTONE_YEARS:
        idx = cal_year - base_year
        if 0 <= idx <= horizon:
            candidate_year_idxs.append(idx)
    if not candidate_year_idxs:
        # Horizon doesn't cover canonical years — fall back to short/mid/long.
        candidate_year_idxs = [
            offset for offset in _MILESTONE_OFFSETS_FALLBACK if offset <= horizon
        ]

    before_by_idx = {int(p["year"]): p for p in before_cone}
    after_by_idx = {int(p["year"]): p for p in after_cone}
    template = _copy()["chart"]["impact_label"]
    for idx in candidate_year_idxs:
        before = before_by_idx.get(idx)
        after = after_by_idx.get(idx)
        if not before or not after:
            continue
        delta = Decimal(str(after.get("p50", 0))) - Decimal(str(before.get("p50", 0)))
        if delta == 0:
            continue
        sign = "+" if delta > 0 else "−"
        label = template.format(
            delta=f"{sign}{format_money_short(abs(delta))}",
            year=base_year + idx,
        )
        labels.append((idx, label))
    return labels


# ---------------------------------------------------------------------------
# Public helper: impact magnitude (P50 delta at a milestone) for narratives + UI
# ---------------------------------------------------------------------------


def p50_delta_at_year(
    before_cone: list[dict],
    after_cone: list[dict],
    year_idx: int,
) -> Decimal:
    before_by_idx = {int(p["year"]): p for p in before_cone}
    after_by_idx = {int(p["year"]): p for p in after_cone}
    before = before_by_idx.get(year_idx)
    after = after_by_idx.get(year_idx)
    if not before or not after:
        return Decimal("0")
    return Decimal(str(after.get("p50", 0))) - Decimal(str(before.get("p50", 0)))


def event_label(event: LifeEvent) -> str:
    """Short user-facing label combining icon + title — used by narrative."""
    meta = _copy()["presets"].get(event.event_type, {})
    icon = meta.get("icon", "")
    base = event.title or meta.get("label", event.event_type)
    return f"{icon} {base}".strip()
