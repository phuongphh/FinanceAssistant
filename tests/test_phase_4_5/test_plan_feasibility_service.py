"""Phase 4.5 / E2 / #2.1 — plan-to-goal feasibility Q&A engine.

``assess`` is pure (no DB, no clock beyond the injected ``today``), so we
drive it directly with fabricated numbers. We check:

* each of the six feasibility bands falls out of the reused engine,
* the honest ``reachable_target`` is conservative (≤ the real ceiling),
  rounds to a clean milestone, and is itself FEASIBLE when fed back in,
* the "already reached" short-circuit,
* determinism (same inputs → same answer; the throw-away goal uuid is
  internal and never leaks into the money math).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.schemas.goal import FeasibilityBand
from backend.services.decision import plan_feasibility_service as svc

TODAY = date(2026, 7, 10)
HORIZON = Decimal("5")  # years
SAVINGS = Decimal("10000000")  # 10tr/month


def _assess(start, target, *, savings=SAVINGS, horizon=HORIZON):
    return svc.assess(
        Decimal(start), Decimal(target), horizon, Decimal(savings), today=TODAY
    )


# --------------------------------------------------------------------------
# The six bands — numbers chosen to sit comfortably inside each range so a
# ±1-month rounding wobble in the horizon can't flip them.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target,expected",
    [
        (200_000_000, FeasibilityBand.EASY),          # ratio ~0.34
        (500_000_000, FeasibilityBand.FEASIBLE),      # ratio ~0.85
        (700_000_000, FeasibilityBand.STRETCH),       # ratio ~1.19
        (1_000_000_000, FeasibilityBand.AMBITIOUS),   # ratio ~1.69
        (2_000_000_000, FeasibilityBand.NEEDS_REVISION),  # ratio ~3.4
    ],
)
def test_bands(target, expected):
    result = _assess(0, target)
    assert result.band == expected


def test_unknown_band_when_no_savings():
    result = _assess(200_000_000, 500_000_000, savings=0)
    assert result.band == FeasibilityBand.UNKNOWN
    # No saving rate → can't grow → reachable collapses to the rounded start.
    assert result.reachable_target == Decimal("200000000")


# --------------------------------------------------------------------------
# Achievable vs. honest-alternative
# --------------------------------------------------------------------------


def test_achievable_bands_have_no_reachable_pivot():
    assert _assess(0, 200_000_000).reachable_target is None  # EASY
    assert _assess(0, 500_000_000).reachable_target is None  # FEASIBLE


def test_reachable_target_is_conservative_and_clean():
    result = _assess(0, 2_000_000_000)  # NEEDS_REVISION
    assert result.reachable_target is not None
    # Never over-promise: reachable ≤ start + savings × months.
    ceiling = Decimal(0) + SAVINGS * Decimal(result.months)
    assert result.reachable_target <= ceiling
    # Clean milestone (multiple of 10tr in the 100tr–1tỷ band).
    assert result.reachable_target % Decimal("10000000") == 0


def test_reachable_target_is_itself_feasible():
    # Pivot must be honest: re-asking with the reachable target lands in an
    # achievable band, not another "cần cố"/"bất khả thi".
    infeasible = _assess(0, 2_000_000_000)
    pivot = _assess(0, infeasible.reachable_target)
    assert pivot.band in {FeasibilityBand.EASY, FeasibilityBand.FEASIBLE}
    assert pivot.reachable_target is None


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


def test_already_reached_short_circuits():
    result = _assess(500_000_000, 200_000_000)
    assert result.already_reached is True
    assert result.band == FeasibilityBand.EASY
    assert result.remaining == Decimal(0)
    assert result.reachable_target is None


def test_remaining_and_required_are_decimal():
    result = _assess(100_000_000, 700_000_000)
    assert isinstance(result.remaining, Decimal)
    assert isinstance(result.required_monthly_savings, Decimal)
    assert result.remaining == Decimal("600000000")


def test_negative_savings_floored_to_zero():
    result = _assess(0, 500_000_000, savings=-5_000_000)
    assert result.actual_monthly_savings == Decimal(0)
    assert result.band == FeasibilityBand.UNKNOWN


def test_deterministic_across_calls():
    # The internal throw-away goal uuid differs each call; the money answer
    # must not.
    a = _assess(50_000_000, 800_000_000)
    b = _assess(50_000_000, 800_000_000)
    assert a.band == b.band
    assert a.remaining == b.remaining
    assert a.reachable_target == b.reachable_target
    assert a.required_monthly_savings == b.required_monthly_savings


def test_months_matches_projection():
    # ``months`` is read back from the projection, so the two never disagree.
    result = _assess(0, 700_000_000)
    assert result.months == result.projection.months_remaining
