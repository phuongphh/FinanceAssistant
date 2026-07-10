"""Phase 4.5 / E1 / Issue #1.4 — shock formatter.

Covers the render rules: weather metaphor with NO percentile numbers, recovery
vs no-recovery copy, the least-harmful redraw list naming only owned classes
(legal-guardrail), the honest shortfall line, and the standalone clarify /
empty-portfolio / confirm strings. Every branch asserts the banned positioning
words never leak into user copy.
"""

from __future__ import annotations

from decimal import Decimal

from backend.bot.formatters.shock import (
    render_clarify_amount,
    render_confirm_large,
    render_empty_portfolio,
    render_shock,
)
from backend.services.decision.liquidation_advisor import rank_options
from backend.services.decision.shock_simulation_service import (
    ShockResult,
    ShockSeverity,
)
from backend.twin.engine.cone_aggregator import ConePoint

_BANNED = ("Decision Engine", "CFO", "GPS")


def _result(
    *, severity: ShockSeverity, recovers: bool, shock=Decimal(200_000_000)
) -> ShockResult:
    baseline = ConePoint(
        year=2036,
        p10=Decimal(800_000_000),
        p50=Decimal(1_500_000_000),
        p90=Decimal(2_500_000_000),
    )
    shocked = ConePoint(
        year=2036,
        p10=Decimal(600_000_000),
        p50=Decimal(1_300_000_000),
        p90=Decimal(2_300_000_000),
    )
    return ShockResult(
        shock_amount=shock,
        horizon_years=10,
        base_net_worth=Decimal(1_000_000_000),
        baseline_final=baseline,
        shocked_final=shocked,
        delta_p10=shocked.p10 - baseline.p10,
        delta_p50=shocked.p50 - baseline.p50,
        delta_p90=shocked.p90 - baseline.p90,
        severity=severity,
        recovers=recovers,
    )


def _plan(shock=Decimal(200_000_000)):
    return rank_options(
        {"cash_savings": Decimal(100_000_000), "gold": Decimal(300_000_000)}, shock
    )


def _assert_clean(text: str):
    assert text
    for banned in _BANNED:
        assert banned not in text


def test_render_shock_uses_weather_not_percentiles():
    out = render_shock(_result(severity=ShockSeverity.HEAVY, recovers=True), _plan())
    _assert_clean(out)
    # Weather metaphor present; raw percentile numbers absent.
    assert "🌧️" in out
    assert "800000000" not in out
    assert "1300000000" not in out
    # Redraw names only owned classes, in least-harmful order.
    assert "tiền gửi" in out  # cash_savings label
    assert "vàng" in out  # gold label
    assert out.index("tiền gửi") < out.index("vàng")


def test_render_shock_recovers_vs_not():
    ok = render_shock(_result(severity=ShockSeverity.LIGHT, recovers=True), _plan())
    bad = render_shock(_result(severity=ShockSeverity.SEVERE, recovers=False), _plan())
    assert "hồi lại" in ok
    assert "khó về lại" in bad
    _assert_clean(ok)
    _assert_clean(bad)


def test_render_shock_shortfall_line_when_underfunded():
    # Shock bigger than everything liquidatable → honest shortfall, no external
    # product suggestion.
    big = Decimal(600_000_000)
    out = render_shock(
        _result(severity=ShockSeverity.SEVERE, recovers=False, shock=big),
        _plan(shock=big),
    )
    assert "còn thiếu" in out
    _assert_clean(out)


def test_standalone_copy_strings_are_clean():
    for text in (
        render_clarify_amount(),
        render_empty_portfolio(),
        render_confirm_large(Decimal(800_000_000)),
    ):
        _assert_clean(text)
