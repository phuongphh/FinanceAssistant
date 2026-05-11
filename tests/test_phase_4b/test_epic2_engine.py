"""Phase 4B Epic 2 — S8 engine tests for apply_life_events / cone_delta_for_event."""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from backend.twin.engine.life_events import (
    LifeEventInjection,
    apply_life_events,
    cone_delta_for_event,
)


BASE_YEAR = 2026
HORIZON_YEARS = 20  # 240 months — matches the S8 spec benchmark.


def _make_paths(initial: float, paths: int, years: int) -> np.ndarray:
    """Build a flat (paths, years+1) array — easy to assert exact shifts on."""
    arr = np.full((paths, years + 1), initial, dtype=np.float64)
    return arr


def test_buy_house_reduces_p50_at_event_year_and_after():
    paths = _make_paths(initial=5_000_000_000, paths=100, years=HORIZON_YEARS)
    event = LifeEventInjection(
        event_id="e1",
        planned_year=2028,
        one_time_cost=3_500_000_000,
        recurring_monthly_delta=0.0,
        recurring_duration_months=0,
    )
    apply_life_events(paths, [event], base_year=BASE_YEAR)
    # Year 2027 (year_offset=1) should be unchanged.
    assert np.allclose(paths[:, 1], 5_000_000_000)
    # Year 2028 (year_offset=2) and beyond should drop by exactly 3.5 tỷ.
    assert np.allclose(paths[:, 2], 1_500_000_000)
    assert np.allclose(paths[:, 5], 1_500_000_000)


def test_recurring_delta_accumulates_monthly():
    paths = _make_paths(initial=10_000_000_000, paths=50, years=HORIZON_YEARS)
    event = LifeEventInjection(
        event_id="e2",
        planned_year=2027,
        one_time_cost=0.0,
        recurring_monthly_delta=-8_000_000,
        recurring_duration_months=216,  # 18 năm — matches the first_child preset
    )
    apply_life_events(paths, [event], base_year=BASE_YEAR, floor_at_zero=False)
    # year_offset=1 → 12 months elapsed → cumulative = -8tr × 12 = -96tr
    assert np.allclose(paths[:, 1], 10_000_000_000 - 96_000_000)
    # year_offset=2 → 24 months → cumulative = -192tr
    assert np.allclose(paths[:, 2], 10_000_000_000 - 192_000_000)
    # year_offset=20 → 240 months, but cap at 216 → cumulative = -8tr × 216 = -1.728 tỷ
    assert np.allclose(paths[:, 20], 10_000_000_000 - 1_728_000_000)


def test_multiple_events_no_double_count():
    paths = _make_paths(initial=10_000_000_000, paths=10, years=HORIZON_YEARS)
    e1 = LifeEventInjection("a", 2028, 1_000_000_000, 0.0, 0)
    e2 = LifeEventInjection("b", 2028, 500_000_000, 0.0, 0)
    apply_life_events(paths, [e1, e2], base_year=BASE_YEAR)
    # Both events at year 2 → total cost 1.5 tỷ applied once each.
    assert np.allclose(paths[:, 2], 10_000_000_000 - 1_500_000_000)


def test_event_beyond_horizon_skipped():
    paths = _make_paths(initial=2_000_000_000, paths=20, years=HORIZON_YEARS)
    event = LifeEventInjection(
        event_id="far",
        planned_year=2999,
        one_time_cost=1_000_000_000,
        recurring_monthly_delta=0.0,
        recurring_duration_months=0,
    )
    apply_life_events(paths, [event], base_year=BASE_YEAR)
    # Nothing should change.
    assert np.allclose(paths, 2_000_000_000)


def test_paths_floored_at_zero():
    paths = _make_paths(initial=1_000_000_000, paths=20, years=HORIZON_YEARS)
    event = LifeEventInjection(
        event_id="big",
        planned_year=2027,
        one_time_cost=5_000_000_000,
        recurring_monthly_delta=0.0,
        recurring_duration_months=0,
    )
    apply_life_events(paths, [event], base_year=BASE_YEAR, floor_at_zero=True)
    # 1 tỷ minus 5 tỷ → would be negative, but floor clamps at 0.
    assert np.all(paths[:, 1:] == 0)
    # Year 0 (before the event) untouched.
    assert np.allclose(paths[:, 0], 1_000_000_000)


def test_event_without_planned_year_is_no_op():
    paths = _make_paths(initial=3_000_000_000, paths=10, years=HORIZON_YEARS)
    event = LifeEventInjection(
        event_id="undated", planned_year=0, one_time_cost=999_999, recurring_monthly_delta=0.0, recurring_duration_months=0
    )
    apply_life_events(paths, [event], base_year=BASE_YEAR)
    assert np.allclose(paths, 3_000_000_000)


def test_indefinite_recurring_treated_as_unlimited():
    """duration_months=0 (early-retirement preset) accrues through the horizon."""
    paths = _make_paths(initial=20_000_000_000, paths=10, years=HORIZON_YEARS)
    event = LifeEventInjection(
        event_id="retire",
        planned_year=2027,
        one_time_cost=0.0,
        recurring_monthly_delta=-25_000_000,
        recurring_duration_months=0,
    )
    apply_life_events(paths, [event], base_year=BASE_YEAR, floor_at_zero=False)
    # year_offset=1 → 12 months × -25tr = -300tr
    assert np.allclose(paths[:, 1], 20_000_000_000 - 300_000_000)
    # year_offset=20 → 240 months × -25tr = -6 tỷ (no cap)
    assert np.allclose(paths[:, 20], 20_000_000_000 - 6_000_000_000)


def test_cone_delta_for_event_matches_path_shift():
    """Deterministic delta API agrees with the engine on flat paths."""
    event = LifeEventInjection(
        "e", 2028, 3_500_000_000, -8_000_000, 240
    )
    deltas = cone_delta_for_event(event, BASE_YEAR, HORIZON_YEARS)
    # Year 2027 (year_offset=1) — event hasn't fired yet, delta should be 0.
    assert deltas[1] == Decimal("0")
    # Year 2028 (year_offset=2) — one-time -3.5 tỷ + 12 months × -8tr = -3.596 tỷ
    assert deltas[2] == Decimal("-3596000000")
    # Year 2029 (year_offset=3) — one-time -3.5 tỷ + 24 months × -8tr = -3.692 tỷ
    assert deltas[3] == Decimal("-3692000000")


def test_benchmark_5_events_under_500ms():
    """The S8 acceptance criterion — 5 events × 1000 paths × 240 months < 500ms."""
    import time

    paths = _make_paths(initial=5_000_000_000, paths=1000, years=HORIZON_YEARS)
    events = [
        LifeEventInjection(f"e{i}", 2027 + i, 1_000_000_000, -5_000_000, 120)
        for i in range(5)
    ]
    start = time.perf_counter()
    apply_life_events(paths, events, base_year=BASE_YEAR)
    elapsed_ms = (time.perf_counter() - start) * 1000
    # We expect well under 50 ms in practice; 500 ms is the spec ceiling.
    assert elapsed_ms < 500, f"engine took {elapsed_ms:.1f}ms (target <500ms)"


def test_zero_amount_events_are_safe_noops():
    paths = _make_paths(initial=1_000_000_000, paths=5, years=HORIZON_YEARS)
    event = LifeEventInjection("noop", 2027, 0.0, 0.0, 0)
    apply_life_events(paths, [event], base_year=BASE_YEAR)
    assert np.allclose(paths, 1_000_000_000)


def test_paths_rejects_nan_input():
    paths = _make_paths(initial=1_000_000_000, paths=5, years=HORIZON_YEARS)
    paths[0, 3] = np.nan
    event = LifeEventInjection("e", 2027, 100_000_000, 0.0, 0)
    with pytest.raises(ValueError):
        apply_life_events(paths, [event], base_year=BASE_YEAR)
