"""Life event injection into Monte Carlo paths — Phase 4B Epic 2 (S8).

Why this lives in the engine layer:
  Phase 4A's MC engine is annual: ``simulate_portfolio`` returns
  ``(n_paths, horizon_years + 1)`` where column ``y`` is "value at end of
  year ``y``". Life events are user inputs with calendar dates and either
  a one-time cash outflow or a monthly recurring outflow over N months.
  Injecting them per-path BEFORE percentile aggregation keeps the cone
  honest — if a 3.5 tỷ down-payment in 2028 pushes some lower-percentile
  paths through zero, the floor-at-zero clamp is reflected in P10.

Mapping calendar → year index:
  ``year_index = planned_date.year - base_year``. The event is treated as
  occurring at the START of that calendar year (by end of the year, the
  one-time cost has been paid and 12 months of recurring delta have
  accrued). This is an approximation: the user only specifies a year in
  the Telegram flow, so we trade per-month precision for simplicity and
  predictable test fixtures.

Performance:
  Pure NumPy, in-place. For 5 events × 1000 paths × 20 years (= 240
  months in the spec) the work is dominated by 5 broadcast subtractions
  on a 1000×20 float64 array — comfortably < 5 ms on commodity hardware,
  well under the 500 ms p95 target in S8.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

import numpy as np
from numpy.typing import NDArray


Array2D = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class LifeEventInjection:
    """Normalized view of a life event for the MC engine.

    Decimal inputs are converted to floats at this boundary so the engine
    stays NumPy-pure. ``recurring_duration_months == 0`` is treated as
    "indefinite" (e.g. early retirement), letting the recurring delta
    accrue through the simulation horizon.
    """

    event_id: str
    planned_year: int
    one_time_cost: float
    recurring_monthly_delta: float
    recurring_duration_months: int  # 0 means indefinite

    @classmethod
    def from_event(cls, event, fallback_event_id: str = "") -> "LifeEventInjection":
        """Adapter from the ``LifeEvent`` SQLAlchemy model (or any duck).

        We avoid importing the SQLAlchemy model here so engine code stays
        DB-agnostic. ``event`` only needs the attributes referenced below.
        """
        planned_date = getattr(event, "planned_date", None)
        planned_year = planned_date.year if isinstance(planned_date, date) else 0
        return cls(
            event_id=str(getattr(event, "id", "") or fallback_event_id),
            planned_year=planned_year,
            one_time_cost=float(getattr(event, "one_time_cost", 0) or 0),
            recurring_monthly_delta=float(
                getattr(event, "recurring_monthly_delta", 0) or 0
            ),
            recurring_duration_months=int(
                getattr(event, "recurring_duration_months", 0) or 0
            ),
        )


def apply_life_events(
    paths: Array2D,
    events: Iterable[LifeEventInjection],
    base_year: int,
    *,
    floor_at_zero: bool = True,
) -> Array2D:
    """Apply life-event cashflows to all MC paths IN PLACE.

    Args:
        paths: ``(n_paths, horizon_years + 1)`` annual net-worth values.
        events: deterministic cashflow events to inject.
        base_year: calendar year corresponding to column 0 (today).
        floor_at_zero: if ``True``, clamp paths to ``≥ 0`` after injection.

    Returns:
        The same ``paths`` array (in-place mutation).

    Each event with a known ``planned_year`` shifts ALL paths uniformly
    in the affected columns, so percentile aggregation produces a cone
    that visibly reflects the event. Events whose year is before
    ``base_year`` are clamped to year 0 (treated as "already today");
    events past the horizon are skipped without raising.
    """
    if paths.ndim != 2 or paths.shape[1] < 2:
        raise ValueError("paths must be a 2D array with year 0 and projected years")
    if not np.isfinite(paths).all():
        raise ValueError("paths contains NaN or Inf before life-event injection")

    horizon = paths.shape[1] - 1  # year 0 + horizon projected years

    for event in events:
        if event.planned_year <= 0:
            # No planned date → event is informational only.
            continue
        year_offset = event.planned_year - base_year
        if year_offset > horizon:
            continue
        year_offset = max(year_offset, 0)

        # One-time cost — subtracted from event year forward.
        if event.one_time_cost:
            paths[:, year_offset:] -= event.one_time_cost

        # Recurring monthly delta — cumulative cashflow accrued per year.
        if event.recurring_monthly_delta:
            year_indices = np.arange(year_offset, horizon + 1, dtype=np.int64)
            months_elapsed = (year_indices - year_offset + 1) * 12
            if event.recurring_duration_months > 0:
                months_capped = np.minimum(
                    months_elapsed, event.recurring_duration_months
                )
            else:
                # Indefinite (e.g. early retirement) — never capped.
                months_capped = months_elapsed
            cumulative = event.recurring_monthly_delta * months_capped.astype(
                np.float64
            )
            # NOTE: ``recurring_monthly_delta`` is signed; we add it directly
            # so a negative delta (outflow) reduces net worth, positive lifts.
            paths[:, year_offset:] += cumulative[np.newaxis, :]

    if floor_at_zero:
        np.maximum(paths, 0, out=paths)

    if not np.isfinite(paths).all():
        raise ValueError("paths contains NaN or Inf after life-event injection")
    return paths


def cone_delta_for_event(
    event: LifeEventInjection,
    base_year: int,
    horizon_years: int,
) -> list[Decimal]:
    """Return the per-year cumulative cashflow impact of one event.

    Each entry is the cumulative delta at end-of-year ``i`` (i = 0..horizon).
    Used by the Mini App's toggle UX: rather than re-running Monte Carlo
    when the user excludes an event, we add or subtract this deterministic
    delta from the stored ``base_cone_data`` percentile-by-percentile.

    Deterministic — independent of stochastic paths.
    """
    deltas = [Decimal("0")] * (horizon_years + 1)
    if event.planned_year <= 0:
        return deltas
    year_offset = max(event.planned_year - base_year, 0)
    if year_offset > horizon_years:
        return deltas
    one_time = Decimal(str(event.one_time_cost))
    monthly = Decimal(str(event.recurring_monthly_delta))
    duration = event.recurring_duration_months

    for year in range(year_offset, horizon_years + 1):
        impact = Decimal("0")
        if event.one_time_cost:
            impact -= one_time
        if event.recurring_monthly_delta:
            months_elapsed = (year - year_offset + 1) * 12
            if duration > 0:
                months_elapsed = min(months_elapsed, duration)
            impact += monthly * Decimal(months_elapsed)
        deltas[year] = impact
    return deltas
