"""Phase 4.5 / E1 / Issue #1.2 — liquidation_advisor.

Covers the pure ranking core: least-harmful draw order (cash → bonds → gold →
stocks → crypto → real estate), greedy spill to the next class, honest shortfall
when the portfolio can't cover the amount, zero/negative balances ignored,
unknown classes sorted last, and non-positive shocks rejected.

legal-guardrail: the plan only ever contains classes present in the input
mapping — there is no path that invents an external product.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services.decision.liquidation_advisor import rank_options


def test_draws_cash_first_then_spills_in_priority_order():
    plan = rank_options(
        {
            "cash_savings": Decimal(100_000_000),
            "stocks_vn": Decimal(300_000_000),
            "gold": Decimal(100_000_000),
        },
        Decimal(250_000_000),
    )
    order = [o.asset_class for o in plan.options]
    # cash (1) → gold (3) → stocks (4); each taken least-harmful first.
    assert order == ["cash_savings", "gold", "stocks_vn"]
    assert plan.options[0].take == Decimal(100_000_000)  # all cash
    assert plan.options[1].take == Decimal(100_000_000)  # all gold
    assert plan.options[2].take == Decimal(50_000_000)  # remainder from stocks
    assert plan.fully_covered is True
    assert plan.shortfall == Decimal(0)


def test_partial_take_leaves_remaining_after():
    plan = rank_options({"cash_savings": Decimal(100_000_000)}, Decimal(30_000_000))
    opt = plan.options[0]
    assert opt.take == Decimal(30_000_000)
    assert opt.remaining_after == Decimal(70_000_000)
    assert plan.fully_covered is True


def test_shortfall_when_portfolio_cannot_cover():
    plan = rank_options({"cash_savings": Decimal(50_000_000)}, Decimal(200_000_000))
    assert plan.fully_covered is False
    assert plan.shortfall == Decimal(150_000_000)
    assert plan.total_liquidatable == Decimal(50_000_000)
    assert plan.has_assets is True


def test_zero_and_negative_balances_ignored():
    plan = rank_options(
        {
            "cash_savings": Decimal(0),
            "gold": Decimal(-5),
            "stocks_vn": Decimal(100_000_000),
        },
        Decimal(40_000_000),
    )
    assert [o.asset_class for o in plan.options] == ["stocks_vn"]


def test_unknown_class_sorts_last():
    plan = rank_options(
        {
            "mystery_class": Decimal(100_000_000),
            "cash_savings": Decimal(100_000_000),
        },
        Decimal(150_000_000),
    )
    # cash first (known priority 1), unknown last (priority 99).
    assert plan.options[0].asset_class == "cash_savings"
    assert plan.options[-1].asset_class == "mystery_class"


def test_empty_portfolio_has_no_assets():
    plan = rank_options({}, Decimal(100_000_000))
    assert plan.has_assets is False
    assert plan.options == ()
    assert plan.fully_covered is False
    assert plan.shortfall == Decimal(100_000_000)


@pytest.mark.parametrize("bad", [Decimal(0), Decimal(-1)])
def test_rejects_non_positive_shock(bad):
    with pytest.raises(ValueError):
        rank_options({"cash_savings": Decimal(10)}, bad)
