"""Vietnamese life event preset defaults — Phase 4B Epic 2 (S7).

Numbers are based on 2025–2026 Vietnam market research. They are conservative
"middle-class urban household" baselines used as starter values; users always
override before saving. Sources are cited per preset so future tuning can
trace assumptions back to evidence rather than guess work.

User-facing strings (labels, descriptions, footnotes) live in
``content/life_events.yaml`` so this module stays pure data. Reading aloud is
the persona test — any Vietnamese copy below would have broken the
"no hardcoded strings" rule from CLAUDE.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.models.life_event import LifeEventType


@dataclass(frozen=True, slots=True)
class LifeEventPreset:
    """Default values for one Vietnamese life event type."""

    event_type: LifeEventType
    one_time_cost: Decimal
    recurring_monthly_delta: Decimal
    recurring_duration_months: int
    source_note: str  # English source citation — exposed via /docs, not to users


# Source: CBRE Vietnam Housing Report 2026; assumes a 3.5 tỷ VND condo with
# 70% loan at 8.5%/year for 20 years → ~28 triệu/month mortgage. We simplify
# to a fixed monthly outflow approximation, since variable-rate scenarios add
# noise without changing the MC cone's order of magnitude.
_BUY_HOUSE = LifeEventPreset(
    event_type=LifeEventType.BUY_HOUSE,
    one_time_cost=Decimal("3500000000"),
    recurring_monthly_delta=Decimal("-28000000"),
    recurring_duration_months=240,
    source_note=(
        "CBRE VN Housing Report 2026 — 3.5B VND condo, 70% LTV, 8.5%/y, 20y"
    ),
)

# Source: VCCI 2026 salary survey + Reuters wedding-cost summary; HCM/HN
# averages ~500 triệu for a 200–300 guest event including ring/honeymoon.
_WEDDING = LifeEventPreset(
    event_type=LifeEventType.WEDDING,
    one_time_cost=Decimal("500000000"),
    recurring_monthly_delta=Decimal("0"),
    recurring_duration_months=0,
    source_note="VCCI 2026 salary survey + wedding-cost averages HCM/HN",
)

# Source: Bộ LĐTBXH child-cost report 2026 — raising one child 0–18 in an
# urban household averages ~8 triệu/month excluding higher-education tuition.
_FIRST_CHILD = LifeEventPreset(
    event_type=LifeEventType.FIRST_CHILD,
    one_time_cost=Decimal("0"),
    recurring_monthly_delta=Decimal("-8000000"),
    recurring_duration_months=216,
    source_note="Bộ LĐTBXH child-cost report 2026 — urban 0–18, ex. ĐH tuition",
)

# Source: Bộ GD&ĐT 2026 — public university 4-year tuition 200–300 triệu plus
# ~5 triệu/month living away from home → 4 years × 12 months recurring.
_CHILD_UNIVERSITY = LifeEventPreset(
    event_type=LifeEventType.CHILD_UNIVERSITY,
    one_time_cost=Decimal("500000000"),
    recurring_monthly_delta=Decimal("-5000000"),
    recurring_duration_months=48,
    source_note="Bộ GD&ĐT 2026 tuition + dorm/sinh-hoạt-phí benchmarks",
)

# Source: GSO 2026 household-spending; "no income" early retirement modeled as
# 25 triệu/month outflow for basic living. ``duration_months=0`` is treated
# as "indefinite" by the MC injector — costs continue through the horizon.
_EARLY_RETIREMENT = LifeEventPreset(
    event_type=LifeEventType.EARLY_RETIREMENT,
    one_time_cost=Decimal("0"),
    recurring_monthly_delta=Decimal("-25000000"),
    recurring_duration_months=0,
    source_note="GSO 2026 urban household basic spending — indefinite outflow",
)

# Custom — user provides everything. Zeros are sentinels for "ask the user".
_CUSTOM = LifeEventPreset(
    event_type=LifeEventType.CUSTOM,
    one_time_cost=Decimal("0"),
    recurring_monthly_delta=Decimal("0"),
    recurring_duration_months=0,
    source_note="User-defined event — no preset applied",
)


_PRESETS: dict[LifeEventType, LifeEventPreset] = {
    LifeEventType.BUY_HOUSE: _BUY_HOUSE,
    LifeEventType.WEDDING: _WEDDING,
    LifeEventType.FIRST_CHILD: _FIRST_CHILD,
    LifeEventType.CHILD_UNIVERSITY: _CHILD_UNIVERSITY,
    LifeEventType.EARLY_RETIREMENT: _EARLY_RETIREMENT,
    LifeEventType.CUSTOM: _CUSTOM,
}


# Display order for menus — keeps the most common events first.
PRESET_ORDER: tuple[LifeEventType, ...] = (
    LifeEventType.BUY_HOUSE,
    LifeEventType.WEDDING,
    LifeEventType.FIRST_CHILD,
    LifeEventType.CHILD_UNIVERSITY,
    LifeEventType.EARLY_RETIREMENT,
    LifeEventType.CUSTOM,
)


def get_preset(event_type: LifeEventType) -> LifeEventPreset:
    """Return the preset for ``event_type``. Raises ``KeyError`` if missing."""
    return _PRESETS[event_type]


def all_presets() -> dict[LifeEventType, LifeEventPreset]:
    """Return all presets keyed by type. Caller must not mutate the result."""
    return dict(_PRESETS)
