from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.market_data.analytics.portfolio_metrics import (
    compute_diversification_score,
    get_best_worst_from_assets,
)


def test_diversification_score_good_for_balanced_portfolio():
    result = compute_diversification_score([
        {"asset_type": "stock", "value": Decimal("40")},
        {"asset_type": "cash", "value": Decimal("30")},
        {"asset_type": "gold", "value": Decimal("20")},
        {"asset_type": "crypto", "value": Decimal("10")},
    ])

    assert result["score"] >= 70
    assert result["label"] == "Tốt"


def test_diversification_score_weak_for_single_asset():
    result = compute_diversification_score([{"asset_type": "stock", "value": Decimal("100")}])

    assert result["score"] < 40
    assert result["label"] == "Yếu"


# ── get_best_worst_from_assets ───────────────────────────────────────
#
# Regression suite for the briefing bug where users saw absurd numbers
# like "Tốt nhất: FPT +29099900.0%" and "yếu nhất: TIỀN MẶT -4569.0%".
# Two root causes are pinned here:
#   1. Cash / real_estate / other have no investment-return semantics —
#      they must be excluded from best/worst ranking.
#   2. When cost-basis data is corrupt (placeholder avg_price, wrong
#      unit), the computed return % explodes. We clip to a sanity range
#      and log a warning instead of rendering nonsense to the user.


def _stub_asset(asset_type: str, symbol: str = "X", asset_id=None):
    """Lightweight Asset stand-in for filter/ordering tests.

    Avoids touching SQLAlchemy session machinery; ``_value_asset`` is
    mocked separately so only the fields read directly by
    ``get_best_worst_from_assets`` and ``_symbol`` need to exist.
    """
    asset = MagicMock()
    asset.id = asset_id or uuid.uuid4()
    asset.asset_type = asset_type
    asset.name = symbol
    asset.extra = {"ticker": symbol}
    asset.initial_value = Decimal("0")
    asset.current_value = Decimal("0")
    return asset


@pytest.mark.asyncio
async def test_cash_is_excluded_from_best_worst_even_with_extreme_drift():
    """Cash with a huge balance change from its onboarding snapshot must
    not surface as a "performer" — the percentage is meaningless and
    historically blew up to thousands of percent in production."""
    cash = _stub_asset("cash", "TIEN MAT")
    cash.initial_value = Decimal("1")          # legacy placeholder
    cash.current_value = Decimal("4500000000")  # 4.5tỷ now

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=AsyncMock(),
    ) as mock_value:
        best, worst = await get_best_worst_from_assets([cash])

    assert best is None and worst is None
    # Filter must happen before valuation: skipping the expensive call
    # is both correct (cash has no cost basis) and a perf win.
    mock_value.assert_not_called()


@pytest.mark.asyncio
async def test_real_estate_and_other_excluded_from_best_worst():
    real_estate = _stub_asset("real_estate", "Apt")
    other = _stub_asset("other", "Misc")

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=AsyncMock(),
    ) as mock_value:
        best, worst = await get_best_worst_from_assets([real_estate, other])

    assert best is None and worst is None
    mock_value.assert_not_called()


@pytest.mark.asyncio
async def test_absurd_positive_pct_filtered_with_warning(caplog):
    """A stock with corrupted avg_price produces millions of % gain —
    must be filtered, not displayed."""
    bad_stock = _stub_asset("stock", "FPT")

    async def fake_value(asset):
        # Simulates avg_price=0.5, current_price=145000 → ~29M%
        return Decimal("14500000"), Decimal("50"), Decimal("28999900")

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        with caplog.at_level("WARNING", logger="backend.market_data.analytics.portfolio_metrics"):
            best, worst = await get_best_worst_from_assets([bad_stock])

    assert best is None and worst is None
    assert any("excluded from best/worst" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_loss_below_neg_100_pct_filtered():
    """Long positions can't lose more than 100% — anything below that
    flags bad data (e.g., negative current_value)."""
    bad_stock = _stub_asset("stock", "BAD")

    async def fake_value(asset):
        return Decimal("0"), Decimal("100"), Decimal("-200")

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        best, worst = await get_best_worst_from_assets([bad_stock])

    assert best is None and worst is None


@pytest.mark.asyncio
async def test_none_pct_skipped():
    """An eligible asset with no cost basis (avg_price=0) returns
    pct=None and must be skipped, not crash."""
    stock = _stub_asset("stock", "SSI")

    async def fake_value(asset):
        return Decimal("100"), Decimal("0"), None

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        best, worst = await get_best_worst_from_assets([stock])

    assert best is None and worst is None


@pytest.mark.asyncio
async def test_normal_performers_sorted_correctly():
    """Multiple eligible holdings with realistic returns rank best to
    worst by return_pct (highest first, lowest last)."""
    stock_a = _stub_asset("stock", "AAA")
    stock_b = _stub_asset("stock", "BBB")
    crypto_c = _stub_asset("crypto", "ETH")
    cash = _stub_asset("cash", "VCB")  # ignored

    returns = {
        stock_a.id: Decimal("5"),
        stock_b.id: Decimal("-3"),
        crypto_c.id: Decimal("12"),
    }

    async def fake_value(asset):
        return Decimal("100"), Decimal("100"), returns[asset.id]

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        best, worst = await get_best_worst_from_assets([stock_a, stock_b, crypto_c, cash])

    assert best["symbol"] == "ETH"
    assert best["return_pct"] == Decimal("12")
    assert worst["symbol"] == "BBB"
    assert worst["return_pct"] == Decimal("-3")


@pytest.mark.asyncio
async def test_single_eligible_asset_returns_same_for_best_and_worst():
    """When only one investment holding has a usable return, best and
    worst point to the same row — the briefing layer collapses this
    into a single 'Hiệu suất:' line instead of best vs. worst."""
    stock = _stub_asset("stock", "VNM")

    async def fake_value(asset):
        return Decimal("100"), Decimal("100"), Decimal("7")

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        best, worst = await get_best_worst_from_assets([stock])

    assert best is not None and worst is not None
    assert best["asset_id"] == worst["asset_id"]
    assert best["symbol"] == "VNM"


@pytest.mark.asyncio
async def test_sanity_boundary_at_minus_100_and_upper_cap_kept():
    """Boundary check: exactly -100% and +1,000,000% are allowed (within
    the closed band). Defends against off-by-one tightening of the guard."""
    stock_loss = _stub_asset("stock", "LOSS")
    stock_moon = _stub_asset("stock", "MOON")

    returns = {
        stock_loss.id: Decimal("-100"),
        stock_moon.id: Decimal("1000000"),
    }

    async def fake_value(asset):
        return Decimal("0"), Decimal("100"), returns[asset.id]

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        best, worst = await get_best_worst_from_assets([stock_loss, stock_moon])

    assert best["symbol"] == "MOON"
    assert worst["symbol"] == "LOSS"


@pytest.mark.asyncio
async def test_legitimate_multi_bagger_kept_in_ranking():
    """A 100x (10,000%) return is unusual but legitimate for long-held
    crypto/stocks. The previous 1000% cap silently dropped these real
    performers; the new generous bound must keep them in the ranking."""
    moonbag = _stub_asset("crypto", "ETH")

    async def fake_value(asset):
        # ETH ICO at ~$0.30 → recent $4000 ≈ 1,300,000% — within new bound.
        return Decimal("4000"), Decimal("30"), Decimal("9900")  # 99x = 9900%

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        best, worst = await get_best_worst_from_assets([moonbag])

    assert best is not None and best["return_pct"] == Decimal("9900")


@pytest.mark.asyncio
async def test_legacy_stocks_alias_recognized_as_eligible():
    """Some assets persisted via the portfolio API carry the plural legacy
    ``asset_type="stocks"`` (see backend/schemas/portfolio.py). Without
    normalization, the filter would silently drop them — the reviewer's
    P2 finding on PR #742."""
    legacy = _stub_asset("stocks", "FPT")

    async def fake_value(asset):
        # _value_asset normalizes "stocks" → "stock" internally and routes
        # to value_stock_holding; the test patches the wrapper directly.
        return Decimal("12000000"), Decimal("9000000"), Decimal("33.33")

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        best, worst = await get_best_worst_from_assets([legacy])

    assert best is not None
    assert best["symbol"] == "FPT"


@pytest.mark.asyncio
async def test_nan_return_pct_skipped_without_crash(caplog):
    """Decimal('NaN') from corrupted cost-basis data must not raise
    InvalidOperation during the range check — guard with is_nan() first."""
    bad = _stub_asset("stock", "BAD")

    async def fake_value(asset):
        return Decimal("100"), Decimal("100"), Decimal("NaN")

    with patch(
        "backend.market_data.analytics.portfolio_metrics._value_asset",
        new=fake_value,
    ):
        with caplog.at_level("WARNING", logger="backend.market_data.analytics.portfolio_metrics"):
            best, worst = await get_best_worst_from_assets([bad])

    assert best is None and worst is None
    assert any("NaN" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_empty_input_returns_none_pair():
    best, worst = await get_best_worst_from_assets([])
    assert best is None and worst is None
