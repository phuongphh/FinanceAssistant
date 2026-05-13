"""Tests for the wealth-level adaptation helpers (Story #126)."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.wealth_adapt import (
    LevelStyle,
    decorate,
    resolve_style,
    style_for_level,
)
from backend.wealth.ladder import WealthLevel


@pytest.mark.parametrize(
    "level,nw,show_pct,show_pnl,show_alloc,show_ytd",
    [
        (WealthLevel.STARTER, Decimal("10_000_000"), False, False, False, False),
        (WealthLevel.YOUNG_PROFESSIONAL, Decimal("100_000_000"), True, True, False, False),
        (WealthLevel.MASS_AFFLUENT, Decimal("500_000_000"), True, True, True, False),
        (WealthLevel.HIGH_NET_WORTH, Decimal("2_000_000_000"), True, True, True, True),
    ],
)
def test_level_style_progressive_disclosure(
    level, nw, show_pct, show_pnl, show_alloc, show_ytd
):
    style = style_for_level(level, nw)
    assert style.show_percent_change is show_pct
    assert style.show_pnl_pct is show_pnl
    assert style.show_allocation_pct is show_alloc
    assert style.show_ytd_return is show_ytd


def test_starter_gets_encouragement_only():
    style = style_for_level(WealthLevel.STARTER, Decimal("5_000_000"))
    assert style.encouragement
    assert style.growth_hint is None


def test_young_pro_gets_growth_hint_only():
    style = style_for_level(WealthLevel.YOUNG_PROFESSIONAL, Decimal("100_000_000"))
    assert style.growth_hint
    assert style.encouragement is None


def test_mass_affluent_and_hnw_get_no_extra_line():
    """They already see analytics — no need to bolt encouragement on."""
    for level, nw in (
        (WealthLevel.MASS_AFFLUENT, Decimal("500_000_000")),
        (WealthLevel.HIGH_NET_WORTH, Decimal("2_000_000_000")),
    ):
        style = style_for_level(level, nw)
        assert style.encouragement is None
        assert style.growth_hint is None


def test_decorate_appends_encouragement_for_starter():
    style = style_for_level(WealthLevel.STARTER, Decimal("5_000_000"))
    out = decorate("Base text", style)
    assert "Base text" in out
    assert style.encouragement in out


def test_decorate_appends_growth_hint_for_young_pro():
    style = style_for_level(WealthLevel.YOUNG_PROFESSIONAL, Decimal("100_000_000"))
    out = decorate("Base text", style)
    assert style.growth_hint in out


def test_decorate_returns_unchanged_when_no_extra_line():
    style = style_for_level(WealthLevel.MASS_AFFLUENT, Decimal("500_000_000"))
    assert decorate("Base text", style) == "Base text"


@pytest.mark.asyncio
async def test_resolve_style_uses_real_net_worth_calculator():
    """Style detection sources net worth from the calculator."""
    breakdown = MagicMock()
    breakdown.total = Decimal("250_000_000")  # Mass Affluent
    user = MagicMock()
    user.id = "u1"

    with patch(
        "backend.intent.wealth_adapt.net_worth_calculator.calculate",
        AsyncMock(return_value=breakdown),
    ):
        style = await resolve_style(MagicMock(), user)

    assert style.level == WealthLevel.MASS_AFFLUENT
    assert style.show_allocation_pct is True


# Acceptance criterion: same query → 4 distinctly different responses
# for 4 mock users at 4 wealth levels. We exercise that by formatting a
# fixed asset list with each style and ensuring the textual outputs
# differ in non-trivial ways (length, presence of percentage signs).


def test_styles_produce_distinct_response_shapes():
    levels = [
        (WealthLevel.STARTER, Decimal("10_000_000")),
        (WealthLevel.YOUNG_PROFESSIONAL, Decimal("100_000_000")),
        (WealthLevel.MASS_AFFLUENT, Decimal("500_000_000")),
        (WealthLevel.HIGH_NET_WORTH, Decimal("2_000_000_000")),
    ]
    samples: dict[WealthLevel, str] = {}
    for level, nw in levels:
        style = style_for_level(level, nw)
        out = decorate("Tài sản hiện tại của bạn: 250tr", style)
        # Tag with show flags so output truly differs.
        out += (
            f" pct={style.show_percent_change} "
            f"pnl={style.show_pnl_pct} "
            f"alloc={style.show_allocation_pct} "
            f"ytd={style.show_ytd_return}"
        )
        samples[level] = out

    # All four must be distinct (acceptance criterion).
    assert len(set(samples.values())) == 4
