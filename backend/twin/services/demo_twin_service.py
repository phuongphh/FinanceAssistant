"""Demo Twin fast-path used by the onboarding "Để Bé Tiền dùng demo trước" button.

The onboarding demo Twin is identical for every user — 50 triệu cash, no
monthly savings, 10-year horizon. Persisting one ``TwinProjection`` row per
user-tap for that fixed input would be wasteful AND brittle: any read-only
flake (FK race during onboarding, DB hiccup) currently surfaces as the
``compute_failed`` fallback even though we have no real recovery for it.

This module computes the demo cone in memory, memoises it for the process
lifetime, and falls back to a hard-coded cone if the Monte Carlo simulation
itself ever raises. The handler then renders the chart directly from the
cone payload — no DB writes, no session state to corrupt.

Determinism: ``seed=0`` and ``paths=500`` give the same cone every call,
which is intentional. Every demo user sees the same picture so we can talk
about it consistently in onboarding copy.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from threading import Lock
from typing import Any

from backend.twin.engine.cone_aggregator import aggregate_cone
from backend.twin.engine.monte_carlo import simulate_portfolio

logger = logging.getLogger(__name__)

DEMO_BASE_NET_WORTH_VND: Decimal = Decimal("50_000_000")
DEMO_HORIZON_YEARS: int = 10
DEMO_SIM_PATHS: int = 500
DEMO_SEED: int = 0

# Hard-coded fallback cone — used if Monte Carlo itself ever raises (numpy
# install regression, OS resource exhaustion, etc.). Generated offline with
# the same parameters as the live simulation; treat it as the "safety net"
# so the user ALWAYS sees a demo Twin even when everything else is broken.
# Values rounded to whole VND to keep the YAML/JSON tiny.
_FALLBACK_CONE: list[dict[str, Any]] = [
    {"year": 0, "p10": "50000000", "p50": "50000000", "p90": "50000000"},
    {"year": 1, "p10": "52000000", "p50": "53000000", "p90": "54000000"},
    {"year": 2, "p10": "54000000", "p50": "56000000", "p90": "58000000"},
    {"year": 3, "p10": "56000000", "p50": "59000000", "p90": "63000000"},
    {"year": 4, "p10": "58000000", "p50": "63000000", "p90": "68000000"},
    {"year": 5, "p10": "61000000", "p50": "66000000", "p90": "73000000"},
    {"year": 6, "p10": "63000000", "p50": "70000000", "p90": "78000000"},
    {"year": 7, "p10": "66000000", "p50": "74000000", "p90": "84000000"},
    {"year": 8, "p10": "69000000", "p50": "78000000", "p90": "90000000"},
    {"year": 9, "p10": "72000000", "p50": "82000000", "p90": "97000000"},
    {"year": 10, "p10": "75000000", "p50": "86000000", "p90": "104000000"},
]

_cone_cache: list[dict[str, Any]] | None = None
_cache_lock = Lock()


def compute_demo_cone() -> list[dict[str, Any]]:
    """Return the cached demo cone (compute on first call, then memoise).

    Always returns a non-empty list. If Monte Carlo fails, returns the
    hard-coded fallback so the caller never has to render an empty chart.
    """
    global _cone_cache
    if _cone_cache is not None:
        return _cone_cache
    with _cache_lock:
        if _cone_cache is not None:
            return _cone_cache
        _cone_cache = _simulate_demo_cone()
        return _cone_cache


def demo_horizon_years() -> int:
    return DEMO_HORIZON_YEARS


def _simulate_demo_cone() -> list[dict[str, Any]]:
    try:
        sim = simulate_portfolio(
            allocation={"cash_savings": DEMO_BASE_NET_WORTH_VND},
            monthly_savings=Decimal("0"),
            savings_split={"cash_savings": Decimal("1")},
            horizon=DEMO_HORIZON_YEARS,
            paths=DEMO_SIM_PATHS,
            seed=DEMO_SEED,
        )
        cone = aggregate_cone(sim)
        return [
            {"year": p.year, "p10": str(p.p10), "p50": str(p.p50), "p90": str(p.p90)}
            for p in cone
        ]
    except Exception:
        logger.exception("Demo Twin Monte Carlo failed; serving hard-coded fallback")
        return list(_FALLBACK_CONE)


def reset_cache_for_tests() -> None:
    """Test hook — forces a recompute on next ``compute_demo_cone`` call."""
    global _cone_cache
    with _cache_lock:
        _cone_cache = None
