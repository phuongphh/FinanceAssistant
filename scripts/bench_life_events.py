#!/usr/bin/env python3
"""Offline benchmark for Phase 4B Epic 2 life-event MC injection (S13).

The S8 spec target is "5 events × 1000 paths × 240 months < 500ms". Our
engine is annual (1000 paths × 20 years), but the broadcast math is the
dominant cost regardless of granularity. This script reports min / p50 /
p95 / max across N runs and exits non-zero if p95 exceeds the budget.

Usage:
    python scripts/bench_life_events.py                    # 50 runs, JSON to stdout
    python scripts/bench_life_events.py --runs 100         # tune sample size
    python scripts/bench_life_events.py --paths 5000       # stress test
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402 — must come after sys.path setup
from backend.twin.engine.life_events import (  # noqa: E402
    LifeEventInjection,
    apply_life_events,
)

BASE_YEAR = 2026
DEFAULT_HORIZON = 20
DEFAULT_PATHS = 1000
DEFAULT_RUNS = 50
P95_BUDGET_MS = 500.0


def _make_events() -> list[LifeEventInjection]:
    """Match the S8 acceptance spec: 5 events, mixed types."""
    return [
        LifeEventInjection("buy_house", 2028, 3_500_000_000, -8_000_000, 240),
        LifeEventInjection("wedding", 2027, 500_000_000, 0.0, 0),
        LifeEventInjection("first_child", 2029, 0.0, -8_000_000, 216),
        LifeEventInjection("child_university", 2046, 500_000_000, -5_000_000, 48),
        LifeEventInjection("early_retirement", 2042, 0.0, -25_000_000, 0),
    ]


def run(*, runs: int, paths: int, horizon: int) -> dict:
    events = _make_events()
    times_ms: list[float] = []
    for _ in range(runs):
        # Recreate paths each iteration so the in-place mutation doesn't compound.
        arr = np.full((paths, horizon + 1), 10_000_000_000, dtype=np.float64)
        t0 = time.perf_counter()
        apply_life_events(arr, events, base_year=BASE_YEAR)
        times_ms.append((time.perf_counter() - t0) * 1000)

    sorted_times = sorted(times_ms)
    summary = {
        "runs": runs,
        "paths": paths,
        "horizon_years": horizon,
        "events": len(events),
        "min_ms": sorted_times[0],
        "p50_ms": statistics.median(sorted_times),
        "p95_ms": sorted_times[int(len(sorted_times) * 0.95) - 1],
        "max_ms": sorted_times[-1],
        "budget_p95_ms": P95_BUDGET_MS,
    }
    summary["p95_within_budget"] = summary["p95_ms"] < P95_BUDGET_MS
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--paths", type=int, default=DEFAULT_PATHS)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    parser.add_argument("--no-fail", action="store_true", help="never exit non-zero")
    args = parser.parse_args()

    summary = run(runs=args.runs, paths=args.paths, horizon=args.horizon)
    print(json.dumps(summary, indent=2))
    if not summary["p95_within_budget"] and not args.no_fail:
        print(
            f"FAIL: p95 {summary['p95_ms']:.1f}ms exceeds budget {P95_BUDGET_MS}ms",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
