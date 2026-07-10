"""Phase 4.5 / E2 / Issues #2.1–#2.3 — feasibility copy + flag.

Pure surface tests for the plan-to-goal feasibility answer:

* #2.1/#2.3 — every band group renders the right tone block, the honest
  reachable-target pivot only shows when there is a real number to offer,
  and ``already_reached`` / ``UNKNOWN`` short-circuit to their own copy.
* #2.2 — ``render_clarify`` asks exactly one warm question and echoes the
  known target on the horizon prompt.
* #2.2 — the ``PLAN_FEASIBILITY_QA_ENABLED`` flag helper defaults off and
  honours the usual truthy/falsy spellings.

``assess`` is pure, so we drive it with fixed inputs + an injected ``today``
and format the real result — no DB, no clock, no mocking of the engine.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.bot.formatters import feasibility as feas_fmt
from backend.intent.handlers import decision_flags
from backend.schemas.goal import FeasibilityBand
from backend.services.decision import plan_feasibility_service

TODAY = date(2026, 7, 10)
_BANNED = ("Decision Engine", "CFO", "GPS")


def _assess(start, target, years, savings):
    return plan_feasibility_service.assess(
        Decimal(start),
        Decimal(target),
        Decimal(years),
        Decimal(savings),
        today=TODAY,
    )


def _render(result, *, target, years):
    return feas_fmt.render_feasibility(
        result, target=Decimal(target), horizon_years=Decimal(years)
    )


def _assert_clean(text: str) -> None:
    for banned in _BANNED:
        assert banned not in text


# --------------------------------------------------------------------------
# Band → tone block
# --------------------------------------------------------------------------


def test_feasible_band_is_encouraging():
    # 0 → 60tr in 5 years needs ~1tr/month; saving 5tr/month is easy.
    result = _assess(0, 60_000_000, 5, 5_000_000)
    assert result.band in (FeasibilityBand.EASY, FeasibilityBand.FEASIBLE)
    text = _render(result, target=60_000_000, years=5)
    assert "trong tầm tay" in text
    # Intro echoes the question back.
    assert "5 năm" in text
    _assert_clean(text)


def test_stretch_band_names_required_and_actual():
    # Needs a step-up but not hopeless: STRETCH/AMBITIOUS.
    result = _assess(0, 100_000_000, 5, 1_200_000)
    assert result.band in (FeasibilityBand.STRETCH, FeasibilityBand.AMBITIOUS)
    text = _render(result, target=100_000_000, years=5)
    assert "cố" in text  # "phải hơi cố chút"
    _assert_clean(text)


def test_needs_revision_never_ends_on_a_flat_no():
    # Way out of reach at the current rate → NEEDS_REVISION + honest pivot.
    result = _assess(0, 5_000_000_000, 2, 1_000_000)
    assert result.band == FeasibilityBand.NEEDS_REVISION
    text = _render(result, target=5_000_000_000, years=2)
    assert "quá sức" in text
    # The reachable pivot is present because there is a positive saving rate.
    assert "với tới được" in text
    _assert_clean(text)


def test_needs_revision_without_savings_drops_the_pivot():
    # No saving rate → no honest reachable number → pivot suppressed.
    result = _assess(0, 5_000_000_000, 2, 0)
    text = _render(result, target=5_000_000_000, years=2)
    # UNKNOWN (no rate) short-circuits to the unknown copy, not a pivot.
    assert result.band == FeasibilityBand.UNKNOWN
    assert "chưa biết" in text
    assert "với tới được" not in text
    _assert_clean(text)


def test_already_reached_short_circuits():
    result = _assess(2_000_000_000, 1_000_000_000, 5, 3_000_000)
    assert result.already_reached is True
    text = _render(result, target=1_000_000_000, years=5)
    assert "trong túi" in text
    _assert_clean(text)


def test_unknown_band_asks_for_cashflow_data():
    result = _assess(0, 1_000_000_000, 5, 0)
    assert result.band == FeasibilityBand.UNKNOWN
    text = _render(result, target=1_000_000_000, years=5)
    assert "chưa biết" in text
    _assert_clean(text)


def test_fractional_years_render_without_trailing_zero():
    result = _assess(0, 60_000_000, Decimal("1.5"), 5_000_000)
    text = _render(result, target=60_000_000, years=Decimal("1.5"))
    assert "1.5 năm" in text
    assert "1.50" not in text


# --------------------------------------------------------------------------
# #2.2 — clarify prompts
# --------------------------------------------------------------------------


def test_clarify_target_asks_for_a_number():
    text = feas_fmt.render_clarify("target")
    assert "con số" in text
    _assert_clean(text)


def test_clarify_horizon_echoes_known_target():
    text = feas_fmt.render_clarify("horizon", target=Decimal(1_000_000_000))
    assert "bao lâu" in text
    # The formatted target appears so the user sees we were listening.
    assert "tỷ" in text or "tỉ" in text
    _assert_clean(text)


# --------------------------------------------------------------------------
# #2.2 — feature flag
# --------------------------------------------------------------------------


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(decision_flags.PLAN_FEASIBILITY_QA_ENABLED_ENV, raising=False)
    assert decision_flags.is_plan_feasibility_qa_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_flag_on(monkeypatch, value):
    monkeypatch.setenv(decision_flags.PLAN_FEASIBILITY_QA_ENABLED_ENV, value)
    assert decision_flags.is_plan_feasibility_qa_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "garbage"])
def test_flag_off(monkeypatch, value):
    monkeypatch.setenv(decision_flags.PLAN_FEASIBILITY_QA_ENABLED_ENV, value)
    assert decision_flags.is_plan_feasibility_qa_enabled() is False
