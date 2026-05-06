"""Income stream type enum + YAML-backed config loader.

Mirror of ``backend.wealth.asset_types`` but for income streams. The
single source of truth is ``content/income_types.yaml`` so adding a
new income category is a one-line YAML edit (the ``stream_type``
column on ``income_streams`` stores the YAML key as a free string,
so no migration is needed).

Phase 3.8 Epic 2 — Story P3.8-S4 acceptance:
    Income types loaded from YAML (`content/income_types.yaml`):
    6 types with metadata (label, is_passive, typical_schedule).
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

import yaml


class StreamType(str, Enum):
    """Stable IDs for income types — what gets written to DB.

    String values must match keys in ``income_types.yaml``. Tests
    enforce that bidirectional mapping via ``test_income_types``.
    """

    SALARY = "salary"
    FREELANCE = "freelance"
    DIVIDEND = "dividend"
    RENTAL = "rental"
    INTEREST = "interest"
    OTHER = "other"


class ScheduleType(str, Enum):
    """How often the income arrives. Drives ``monthly_equivalent``
    math on the model.

    - ``monthly``   — most common (salary, rent)
    - ``quarterly`` — some Vietnamese stocks pay quarterly
    - ``annually``  — typical VN dividend rhythm
    - ``ad_hoc``    — freelance / consulting / sporadic
    """

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"
    AD_HOC = "ad_hoc"


_INCOME_TYPES_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "income_types.yaml"
)


@lru_cache(maxsize=1)
def load_income_types() -> dict:
    """Read the YAML once per process; tests can call ``cache_clear``
    after fiddling with the file."""
    with open(_INCOME_TYPES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_income_type_config(stream_type: str) -> dict:
    """Full config for one type (label, icon, is_passive, ...).

    Returns ``{}`` for unknown keys — callers fall back to a generic
    icon/label so a typo or future YAML lag doesn't crash the bot.
    """
    return load_income_types().get("income_types", {}).get(stream_type, {})


def get_label(stream_type: str) -> str:
    return get_income_type_config(stream_type).get("label", stream_type)


def get_icon(stream_type: str) -> str:
    return get_income_type_config(stream_type).get("icon", "💰")


def is_passive_default(stream_type: str) -> bool:
    """Default ``is_passive`` flag for a type. Wizard uses this if
    the user doesn't explicitly pick. Spec defaults align with VN
    tax/financial conventions: rental and dividend = passive."""
    return bool(get_income_type_config(stream_type).get("is_passive", False))


def typical_schedule(stream_type: str) -> str:
    """Pre-fill the wizard's schedule pick. Reduces taps for the
    80% case (salary → monthly, dividend → annually, etc.)."""
    return get_income_type_config(stream_type).get("typical_schedule", "monthly")


def is_auto_linked(stream_type: str) -> bool:
    """``True`` if streams of this type are created by another module
    (currently only rental, which is auto-created when a real-estate
    asset is marked as rental). Used by the wizard to hide these from
    the "Add new" picker."""
    return bool(get_income_type_config(stream_type).get("auto_linked", False))


def all_user_facing_types() -> list[str]:
    """List of types the wizard offers to the user — auto-linked
    types are excluded so the user doesn't try to manually create a
    rental stream (it's created from the asset wizard instead)."""
    types = load_income_types().get("income_types", {})
    return [t for t in types if not types[t].get("auto_linked", False)]


__all__ = [
    "StreamType",
    "ScheduleType",
    "load_income_types",
    "get_income_type_config",
    "get_label",
    "get_icon",
    "is_passive_default",
    "typical_schedule",
    "is_auto_linked",
    "all_user_facing_types",
]
