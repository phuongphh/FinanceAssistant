"""Phase 4.5 / E2 / Issue #2.2 — DecisionFeasibilityHandler wiring.

The handler is the flag-gated edge in front of the pure ``assess`` + formatter:

* Flag dark → delegate to the generic ``AdvisoryHandler`` unchanged.
* Flag on, missing an essential param → exactly one warm clarify question
  (target first, then horizon echoing the known target).
* Flag on, full params → a single ``get_avg_monthly_savings`` read, then the
  formatted verdict.
* ``_coerce_amount`` / ``_coerce_years`` reject junk so the handler asks
  instead of guessing, and clamp a fat-fingered horizon.

We fake the User + session (the one DB call is monkeypatched) so these stay
DB-free and fast.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.intent.handlers import advisory as advisory_mod
from backend.intent.handlers import decision_feasibility as dfh
from backend.intent.handlers.decision_feasibility import (
    DecisionFeasibilityHandler,
    _coerce_amount,
    _coerce_years,
)
from backend.intent.intents import IntentResult, IntentType

FLAG = "PLAN_FEASIBILITY_QA_ENABLED"


def _intent(**params) -> IntentResult:
    return IntentResult(
        intent=IntentType.DECISION_FEASIBILITY,
        confidence=0.8,
        parameters=dict(params),
        raw_text="muốn có 1 tỷ sau 5 năm khả thi không",
    )


def _user():
    return SimpleNamespace(id=uuid.uuid4(), salutation="bạn")


# --------------------------------------------------------------------------
# Flag gating
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_delegates_to_advisory(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)

    seen = {}

    class FakeAdvisory:
        async def handle(self, intent, user, db):
            seen["called"] = True
            return "ADVISORY_FALLBACK"

    monkeypatch.setattr(advisory_mod, "AdvisoryHandler", FakeAdvisory)

    out = await DecisionFeasibilityHandler().handle(
        _intent(target_amount=1_000_000_000, horizon_years=5), _user(), None
    )
    assert out == "ADVISORY_FALLBACK"
    assert seen.get("called") is True


@pytest.mark.asyncio
async def test_flag_on_missing_target_clarifies(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    out = await DecisionFeasibilityHandler().handle(
        _intent(horizon_years=5), _user(), None
    )
    assert "con số" in out  # clarify_target copy


@pytest.mark.asyncio
async def test_flag_on_missing_horizon_clarifies_and_echoes_target(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    out = await DecisionFeasibilityHandler().handle(
        _intent(target_amount=1_000_000_000), _user(), None
    )
    assert "bao lâu" in out  # clarify_horizon copy
    assert "tỷ" in out or "tỉ" in out  # echoes the known target


@pytest.mark.asyncio
async def test_flag_on_full_params_renders_verdict(monkeypatch):
    monkeypatch.setenv(FLAG, "true")

    async def fake_savings(db, user_id, *, today=None):
        return Decimal(5_000_000)

    monkeypatch.setattr(dfh, "get_avg_monthly_savings", fake_savings)

    out = await DecisionFeasibilityHandler().handle(
        _intent(target_amount=60_000_000, horizon_years=5), _user(), object()
    )
    # 5tr/month easily clears a 60tr / 5yr goal → encouraging verdict.
    assert "trong tầm tay" in out
    assert "5 năm" in out


@pytest.mark.asyncio
async def test_start_amount_is_optional(monkeypatch):
    monkeypatch.setenv(FLAG, "true")

    async def fake_savings(db, user_id, *, today=None):
        return Decimal(1_000_000)

    monkeypatch.setattr(dfh, "get_avg_monthly_savings", fake_savings)

    # No start_amount → starts fresh (0); still produces a verdict, not a crash.
    out = await DecisionFeasibilityHandler().handle(
        _intent(target_amount=1_000_000_000, horizon_years=10), _user(), object()
    )
    assert out
    for banned in ("Decision Engine", "CFO", "GPS"):
        assert banned not in out


# --------------------------------------------------------------------------
# Coercion helpers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (1_000_000_000, Decimal(1_000_000_000)),
        ("500000000", Decimal(500_000_000)),
        ("  1000000  ", Decimal(1_000_000)),
        (Decimal("250000000"), Decimal(250_000_000)),
    ],
)
def test_coerce_amount_accepts_positive_numbers(value, expected):
    assert _coerce_amount(value) == expected


@pytest.mark.parametrize("value", [None, True, False, 0, -5, "abc", "", "  "])
def test_coerce_amount_rejects_junk(value):
    assert _coerce_amount(value) is None


@pytest.mark.parametrize(
    "value,expected",
    [(5, Decimal(5)), ("1.5", Decimal("1.5")), ("10", Decimal(10))],
)
def test_coerce_years_accepts_positive(value, expected):
    assert _coerce_years(value) == expected


@pytest.mark.parametrize("value", [None, True, 0, -1, "0", "junk"])
def test_coerce_years_rejects_junk(value):
    assert _coerce_years(value) is None


def test_coerce_years_clamps_absurd_horizon():
    # A fat-fingered "500 năm" can't spin the projection off the rails.
    assert _coerce_years(500) == dfh._MAX_HORIZON_YEARS
