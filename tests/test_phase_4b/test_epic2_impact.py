"""Phase 4B Epic 2 — read-time impact helpers (used by Mini App + chart)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal


from backend.life_events.impact import (
    adjust_cone_with_events,
    build_impact_summary,
    parse_event_ids,
)
from backend.models.life_event import LifeEvent, LifeEventType


BASE_YEAR = 2026


def _make_event(
    event_type: LifeEventType = LifeEventType.BUY_HOUSE,
    planned_year: int = 2028,
    one_time: Decimal = Decimal("3500000000"),
    monthly: Decimal = Decimal("-8000000"),
    duration: int = 240,
    title: str = "Mua nhà",
) -> LifeEvent:
    event = LifeEvent()
    event.id = __import__("uuid").uuid4()
    event.event_type = event_type.value
    event.title = title
    event.planned_date = date(planned_year, 1, 1)
    event.one_time_cost = one_time
    event.recurring_monthly_delta = monthly
    event.recurring_duration_months = duration
    event.is_active = True
    return event


def _flat_cone(value: int, horizon: int = 10) -> list[dict]:
    return [
        {"year": y, "p10": str(value), "p50": str(value), "p90": str(value)}
        for y in range(horizon + 1)
    ]


def test_adjust_cone_subtracts_one_time_cost_after_event_year():
    base = _flat_cone(value=10_000_000_000, horizon=10)
    events = [_make_event(planned_year=2028, one_time=Decimal("3500000000"), monthly=Decimal("0"), duration=0)]
    adjusted = adjust_cone_with_events(base, events, BASE_YEAR)
    # Years before 2028 (idx<2) unchanged.
    assert Decimal(adjusted[0]["p50"]) == Decimal("10000000000")
    assert Decimal(adjusted[1]["p50"]) == Decimal("10000000000")
    # Year 2028 (idx=2) onwards drops by 3.5 tỷ.
    assert Decimal(adjusted[2]["p50"]) == Decimal("6500000000")
    assert Decimal(adjusted[5]["p50"]) == Decimal("6500000000")


def test_adjust_cone_floors_at_zero_for_p10():
    base = _flat_cone(value=1_000_000_000, horizon=5)
    events = [_make_event(planned_year=2027, one_time=Decimal("5000000000"), monthly=Decimal("0"), duration=0)]
    adjusted = adjust_cone_with_events(base, events, BASE_YEAR)
    # idx=1+ would be negative — must clamp to 0 to mirror the engine.
    assert Decimal(adjusted[1]["p10"]) == Decimal("0")
    assert Decimal(adjusted[1]["p50"]) == Decimal("0")


def test_adjust_cone_with_empty_events_is_passthrough():
    base = _flat_cone(value=5_000_000_000, horizon=3)
    adjusted = adjust_cone_with_events(base, [], BASE_YEAR)
    for orig, adj in zip(base, adjusted):
        assert Decimal(orig["p50"]) == Decimal(adj["p50"])


def test_build_impact_summary_includes_year_deltas_and_totals():
    event = _make_event(
        planned_year=2028,
        one_time=Decimal("3500000000"),
        monthly=Decimal("-8000000"),
        duration=240,
    )
    summary = build_impact_summary(event, base_year=BASE_YEAR, horizon_years=10)
    assert summary.event_type == LifeEventType.BUY_HOUSE
    assert summary.planned_year == 2028
    assert summary.one_time_cost == Decimal("3500000000")
    # 240 months × -8tr/mo
    assert summary.recurring_total_cost == Decimal("-1920000000")
    # Deltas indexed by year offset from BASE_YEAR (2026).
    assert summary.year_deltas[0] == Decimal("0")
    assert summary.year_deltas[1] == Decimal("0")
    # At idx=2 (2028): -3.5 tỷ + 12 months × -8tr = -3.596 tỷ
    assert summary.year_deltas[2] == Decimal("-3596000000")


def test_parse_event_ids_drops_invalid_tokens():
    valid = "11111111-1111-1111-1111-111111111111"
    raw = f" {valid} , garbage , ,22222222-2222-2222-2222-222222222222 "
    result = parse_event_ids(raw)
    assert len(result) == 2


def test_parse_event_ids_empty_returns_empty_set():
    assert parse_event_ids(None) == set()
    assert parse_event_ids("") == set()
    assert parse_event_ids("   ,  , ") == set()


def test_multiple_events_combine_additively():
    base = _flat_cone(value=10_000_000_000, horizon=10)
    e1 = _make_event(
        planned_year=2027, one_time=Decimal("500000000"), monthly=Decimal("0"), duration=0
    )
    e2 = _make_event(
        planned_year=2027, one_time=Decimal("300000000"), monthly=Decimal("0"), duration=0
    )
    adjusted = adjust_cone_with_events(base, [e1, e2], BASE_YEAR)
    # Both events at 2027 (idx=1) → total -800tr
    assert Decimal(adjusted[1]["p50"]) == Decimal("9200000000")
