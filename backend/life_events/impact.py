"""Deterministic life-event impact helpers for read-time UX.

Given a stored ``base_cone_data`` (computed without any events) and a list
of active life events, this module produces:

- per-event ``year_deltas`` for toggle UI (the Mini App can add/subtract
  these from the base cone without re-running Monte Carlo);
- an adjusted cone for an arbitrary subset of events (default = all
  active), used by the ``GET /api/twin?exclude_event_ids=…`` endpoint.

This is intentionally separate from the engine-layer ``apply_life_events``:
that one mutates stochastic paths; this one operates on aggregated cone
points. The two agree on a deterministic shift (one_time_cost +
cumulative recurring) but differ at extreme percentiles when paths
get clamped to zero by the floor — read-time adjustment can't recover
that information, which is why the default API path returns the stored
(with-events) cone rather than recomputing from base.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Sequence

from backend.life_events.schemas import LifeEventImpact
from backend.models.life_event import LifeEvent, LifeEventType
from backend.twin.engine.life_events import (
    LifeEventInjection,
    cone_delta_for_event,
)


_CONE_KEYS = ("p10", "p50", "p90")


def event_to_injection(event: LifeEvent) -> LifeEventInjection:
    """Adapter from ORM row → engine struct. Pure function, no I/O."""
    return LifeEventInjection.from_event(event)


def build_impact_summary(
    event: LifeEvent,
    base_year: int,
    horizon_years: int,
) -> LifeEventImpact:
    """Return the per-event year-delta summary used by Mini App + Telegram."""
    injection = event_to_injection(event)
    deltas = cone_delta_for_event(injection, base_year, horizon_years)
    one_time = Decimal(str(event.one_time_cost or 0))
    duration = int(event.recurring_duration_months or 0)
    monthly = Decimal(str(event.recurring_monthly_delta or 0))
    recurring_total = monthly * Decimal(duration) if duration > 0 else Decimal("0")
    return LifeEventImpact(
        event_id=event.id,
        event_type=LifeEventType(event.event_type)
        if event.event_type in {t.value for t in LifeEventType}
        else LifeEventType.CUSTOM,
        title=event.title,
        planned_year=event.planned_date.year if event.planned_date else None,
        one_time_cost=one_time,
        recurring_total_cost=recurring_total,
        year_deltas=deltas,
    )


def adjust_cone_with_events(
    base_cone: Sequence[dict],
    events: Iterable[LifeEvent],
    base_year: int,
) -> list[dict]:
    """Apply a subset of events to a base cone deterministically.

    The cone is a list of ``{"year": int, "p10": str, "p50": str, "p90": str}``
    points. We add each event's cumulative year delta to all three
    percentiles, then floor at zero to mirror the engine's clamping.

    Pure function — does not mutate ``base_cone``.
    """
    if not base_cone:
        return []
    horizon_years = max(int(point.get("year", 0)) for point in base_cone)
    aggregated_deltas: list[Decimal] = [Decimal("0")] * (horizon_years + 1)
    for event in events:
        injection = event_to_injection(event)
        deltas = cone_delta_for_event(injection, base_year, horizon_years)
        for idx, delta in enumerate(deltas):
            if idx < len(aggregated_deltas):
                aggregated_deltas[idx] += delta

    adjusted: list[dict] = []
    for point in base_cone:
        year = int(point.get("year", 0))
        delta = aggregated_deltas[year] if year < len(aggregated_deltas) else Decimal("0")
        new_point = {"year": year}
        for key in _CONE_KEYS:
            raw = point.get(key)
            if raw is None:
                new_point[key] = "0"
                continue
            value = Decimal(str(raw)) + delta
            if value < 0:
                value = Decimal("0")
            new_point[key] = str(value.quantize(Decimal("1")))
        adjusted.append(new_point)
    return adjusted


def parse_event_ids(raw: str | None) -> set[uuid.UUID]:
    """Parse a comma-separated event-id query param. Invalid UUIDs are dropped.

    The router uses this to validate ``exclude_event_ids=...`` without
    failing the whole request when one of several IDs is malformed —
    skipping invalid IDs is more useful than 400-ing the whole twin view.
    """
    if not raw:
        return set()
    result: set[uuid.UUID] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            result.add(uuid.UUID(token))
        except (ValueError, AttributeError):
            continue
    return result


def base_year_from_computed_at(computed_at: datetime | None) -> int:
    """Return the calendar year corresponding to cone column 0."""
    if computed_at is None:
        return datetime.utcnow().year
    return computed_at.year
