"""Loader for ``content/goal_templates.yaml`` (Phase 3.8 Epic 5).

Mirrors ``backend.wealth.income_types`` and ``backend.wealth.asset_types``:
single source of truth in YAML, ``lru_cache``-d loader, lookup
helpers that fall back gracefully on unknown ids.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml


@dataclass(frozen=True)
class GoalTemplate:
    """In-memory representation of one row in goal_templates.yaml.

    Frozen so the cached list returned by ``list_templates`` can be
    safely shared across requests.
    """

    id: str
    name: str
    category: str
    icon: str
    min_amount: Decimal
    max_amount: Decimal
    min_months: int
    max_months: int
    description: Optional[str] = None
    suggested_questions: tuple[str, ...] = ()


_GOAL_TEMPLATES_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "goal_templates.yaml"
)


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    with open(_GOAL_TEMPLATES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def list_templates() -> list[GoalTemplate]:
    """Return all 7 templates in YAML order. Cached — YAML edits in
    production require a process restart, same convention as
    ``income_types`` / ``menu_copy`` loaders."""
    raw = _load_raw().get("templates", [])
    out: list[GoalTemplate] = []
    for entry in raw:
        amount_range = entry.get("typical_amount_range") or [0, 0]
        timeline_range = entry.get("typical_timeline_months") or [0, 0]
        out.append(GoalTemplate(
            id=entry["id"],
            name=entry["name"],
            category=entry.get("category", "other"),
            icon=entry.get("icon", "🎯"),
            min_amount=Decimal(str(amount_range[0])),
            max_amount=Decimal(str(amount_range[1])),
            min_months=int(timeline_range[0]),
            max_months=int(timeline_range[1]),
            description=entry.get("description"),
            suggested_questions=tuple(entry.get("suggested_questions") or []),
        ))
    return out


def get_template(template_id: str) -> Optional[GoalTemplate]:
    """Single-template lookup by id. Returns ``None`` (not raising)
    so callers can branch on missing — e.g. a template removed from
    YAML still has rows in DB referencing the dropped id."""
    for t in list_templates():
        if t.id == template_id:
            return t
    return None


def get_icon(template_id: str | None) -> str:
    """Icon for a template, with a sensible fallback for custom or
    legacy goals where ``template_id`` is null/unknown."""
    if not template_id:
        return "🎯"
    t = get_template(template_id)
    return t.icon if t else "🎯"


__all__ = [
    "GoalTemplate",
    "list_templates",
    "get_template",
    "get_icon",
]
