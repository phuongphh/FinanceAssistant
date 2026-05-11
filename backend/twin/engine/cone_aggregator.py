"""Probability-cone aggregation for Phase 4A Financial Twin."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class ConePoint:
    """Percentile cone values for one projection year."""

    year: int
    p10: Decimal
    p50: Decimal
    p90: Decimal


def aggregate_cone(
    sim_result: NDArray[np.float64],
    percentiles: Sequence[int] = (10, 50, 90),
) -> list[ConePoint]:
    """Aggregate paths into P10/P50/P90 cone points rounded to 1,000 VND."""
    if tuple(percentiles) != (10, 50, 90):
        raise ValueError("Phase 4A cone supports percentiles=[10, 50, 90]")
    if sim_result.ndim != 2 or sim_result.shape[1] < 2:
        raise ValueError("sim_result must be a 2D array with year 0 and projected years")
    if not np.isfinite(sim_result).all():
        raise ValueError("sim_result contains NaN or Inf")

    raw = np.percentile(sim_result, percentiles, axis=0).T
    cone: list[ConePoint] = []
    for year, (p10, p50, p90) in enumerate(raw):
        point = ConePoint(
            year=year,
            p10=_round_vnd(p10),
            p50=_round_vnd(p50),
            p90=_round_vnd(p90),
        )
        if not (point.p10 <= point.p50 <= point.p90):
            raise AssertionError(f"Cone percentiles are not monotonic for year {year}")
        cone.append(point)
    return cone


def _round_vnd(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("1E+3"), rounding=ROUND_HALF_UP)
