"""Demo Twin fast-path used by the onboarding "Để Bé Tiền dùng demo trước" button.

The onboarding demo Twin is identical for every user — a 50 triệu diversified
portfolio split across 2 asset classes (30tr cash savings + 20tr VN stocks),
no monthly savings, 10-year horizon. Persisting one ``TwinProjection`` row per
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

Why 2 asset classes: a single cash bucket produced a near-straight P50
line that looked under-impressive and undersold what a real diversified
portfolio can do. The 60/40 cash/stocks split shows visible upside from
diversification — closer to what a typical mass-affluent user will see
once they enter their real assets.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from threading import Lock
from typing import Any

from backend.twin.engine.cone_aggregator import aggregate_cone
from backend.twin.engine.monte_carlo import simulate_portfolio

logger = logging.getLogger(__name__)

DEMO_CASH_VND: Decimal = Decimal("30_000_000")
DEMO_STOCKS_VN_VND: Decimal = Decimal("20_000_000")
DEMO_BASE_NET_WORTH_VND: Decimal = DEMO_CASH_VND + DEMO_STOCKS_VN_VND
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
    {"year": 1, "p10": "48541000", "p50": "54097000", "p90": "61065000"},
    {"year": 2, "p10": "50435000", "p50": "57766000", "p90": "68959000"},
    {"year": 3, "p10": "52573000", "p50": "62158000", "p90": "79052000"},
    {"year": 4, "p10": "54951000", "p50": "67813000", "p90": "88620000"},
    {"year": 5, "p10": "58314000", "p50": "73095000", "p90": "99506000"},
    {"year": 6, "p10": "61371000", "p50": "79074000", "p90": "116483000"},
    {"year": 7, "p10": "63968000", "p50": "83654000", "p90": "136166000"},
    {"year": 8, "p10": "68085000", "p50": "91474000", "p90": "155966000"},
    {"year": 9, "p10": "70535000", "p50": "99358000", "p90": "171732000"},
    {"year": 10, "p10": "73650000", "p50": "109619000", "p90": "196684000"},
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
            allocation={
                "cash_savings": DEMO_CASH_VND,
                "stocks_vn": DEMO_STOCKS_VN_VND,
            },
            monthly_savings=Decimal("0"),
            savings_split={
                "cash_savings": Decimal("0.6"),
                "stocks_vn": Decimal("0.4"),
            },
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
