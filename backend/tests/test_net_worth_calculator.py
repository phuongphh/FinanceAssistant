"""Unit tests for ``backend.wealth.services.net_worth_calculator``.

We mock ``asset_service.get_user_assets`` (sync-replace via monkeypatch)
and ``db.execute`` so we can exercise the breakdown / historical /
change paths without a real Postgres.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.wealth.models.asset import Asset
from backend.wealth.services import net_worth_calculator as nwc


def _asset(asset_type: str, name: str, value: Decimal | int) -> Asset:
    return Asset(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        asset_type=asset_type,
        name=name,
        initial_value=Decimal(value),
        current_value=Decimal(value),
        acquired_at=date.today(),
        is_active=True,
    )


@pytest.mark.asyncio
class TestCalculate:
    async def test_empty_assets_returns_zero(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[]),
        )
        breakdown = await nwc.calculate(MagicMock(), uuid.uuid4())
        assert breakdown.total == Decimal(0)
        assert breakdown.by_type == {}
        assert breakdown.asset_count == 0
        assert breakdown.largest_asset == (None, Decimal(0))

    async def test_breakdown_by_type(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(
                return_value=[
                    _asset("cash", "VCB", 50_000_000),
                    _asset("cash", "MoMo", 5_000_000),
                    _asset("stock", "VNM", 20_000_000),
                    _asset("real_estate", "Nhà Mỹ Đình", 2_000_000_000),
                ]
            ),
        )
        b = await nwc.calculate(MagicMock(), uuid.uuid4())
        assert b.total == Decimal("2_075_000_000")
        assert b.asset_count == 4
        assert b.by_type["cash"] == Decimal("55_000_000")
        assert b.by_type["stock"] == Decimal("20_000_000")
        assert b.by_type["real_estate"] == Decimal("2_000_000_000")
        assert b.largest_asset == ("Nhà Mỹ Đình", Decimal("2_000_000_000"))

    async def test_live_valuation_batches_stock_and_crypto_calls(self, monkeypatch):
        # Issue #797 follow-up: ``calculate`` must NOT issue one HTTP
        # call per holding. The batched helpers should be invoked exactly
        # once each, and the live stock/crypto/gold valuations should
        # override the stored ``current_value`` in the total.
        stock_calls = 0
        crypto_calls = 0
        gold_calls = 0

        async def fake_stock_holdings(assets):
            nonlocal stock_calls
            stock_calls += 1
            stocks = [a for a in assets if a.asset_type == "stock"]
            # Pretend the live quote doubled the stored value for each
            # stock; the total should reflect the live value.
            from backend.wealth.valuation.stock import HoldingValuation
            return {
                a: HoldingValuation(
                    current_price=Decimal(a.current_value or 0) * 2,
                    quantity=Decimal(1),
                    cost_basis=Decimal(a.current_value or 0),
                    current_value=Decimal(a.current_value or 0) * 2,
                    pnl_pct=Decimal(100),
                    is_stale=False,
                )
                for a in stocks
            }

        async def fake_crypto_holdings(assets):
            nonlocal crypto_calls
            crypto_calls += 1
            cryptos = [a for a in assets if a.asset_type == "crypto"]
            from backend.wealth.valuation.crypto import HoldingValuation
            return {
                a: HoldingValuation(
                    current_price=Decimal(a.current_value or 0) * 3,
                    quantity=Decimal(1),
                    cost_basis=Decimal(a.current_value or 0),
                    current_value=Decimal(a.current_value or 0) * 3,
                    pnl_pct=Decimal(200),
                    is_stale=False,
                )
                for a in cryptos
            }

        async def fake_gold_holdings(assets):
            nonlocal gold_calls
            gold_calls += 1
            golds = [a for a in assets if a.asset_type == "gold"]
            from backend.wealth.valuation.gold import HoldingValuation
            return {
                a: HoldingValuation(
                    current_price=Decimal(a.current_value or 0) * 4,
                    quantity=Decimal(1),
                    cost_basis=Decimal(a.current_value or 0),
                    current_value=Decimal(a.current_value or 0) * 4,
                    pnl_pct=Decimal(300),
                    is_stale=False,
                )
                for a in golds
            }

        monkeypatch.setattr(nwc, "value_stock_holdings", fake_stock_holdings)
        monkeypatch.setattr(nwc, "value_crypto_holdings", fake_crypto_holdings)
        monkeypatch.setattr(nwc, "value_gold_holdings", fake_gold_holdings)
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(
                return_value=[
                    _asset("stock", "VNM", 10_000_000),
                    _asset("stock", "HPG", 20_000_000),
                    _asset("crypto", "BTC", 30_000_000),
                    _asset("gold", "SJC", 40_000_000),
                    _asset("cash", "VCB", 50_000_000),
                ]
            ),
        )

        breakdown = await nwc.calculate(MagicMock(), uuid.uuid4())

        # One batched call per asset class, regardless of holding count.
        assert stock_calls == 1
        assert crypto_calls == 1
        assert gold_calls == 1
        # Stocks doubled, crypto tripled, gold quadrupled by the fake live
        # valuation; cash uses stored value.
        assert breakdown.by_type["stock"] == Decimal("60_000_000")
        assert breakdown.by_type["crypto"] == Decimal("90_000_000")
        assert breakdown.by_type["gold"] == Decimal("160_000_000")
        assert breakdown.by_type["cash"] == Decimal("50_000_000")
        assert breakdown.total == Decimal("360_000_000")

    async def test_stored_current_skips_live_market_valuation(self, monkeypatch):
        async def fail_live_valuation(*_args, **_kwargs):
            raise AssertionError("stored-current path must not call live valuation")

        monkeypatch.setattr(nwc, "value_stock_holdings", fail_live_valuation)
        monkeypatch.setattr(nwc, "value_crypto_holdings", fail_live_valuation)
        monkeypatch.setattr(nwc, "value_gold_holdings", fail_live_valuation)
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(
                return_value=[
                    _asset("stock", "VNM", 20_000_000),
                    _asset("crypto", "BTC", 30_000_000),
                    _asset("cash", "VCB", 50_000_000),
                ]
            ),
        )

        breakdown = await nwc.calculate_stored_current(MagicMock(), uuid.uuid4())

        assert breakdown.total == Decimal("100_000_000")
        assert breakdown.asset_count == 3
        assert breakdown.by_type["stock"] == Decimal("20_000_000")
        assert breakdown.by_type["crypto"] == Decimal("30_000_000")
        assert breakdown.by_type["cash"] == Decimal("50_000_000")
        assert breakdown.largest_asset == ("VCB", Decimal("50_000_000"))


@pytest.mark.asyncio
class TestCalculateHistorical:
    async def test_returns_sum_from_query(self):
        result = MagicMock()
        result.scalar.return_value = Decimal("123_000_000")
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        total = await nwc.calculate_historical(db, uuid.uuid4(), date(2026, 4, 1))
        assert total == Decimal("123_000_000")

    async def test_no_snapshots_returns_zero(self):
        result = MagicMock()
        result.scalar.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        total = await nwc.calculate_historical(db, uuid.uuid4(), date(2026, 4, 1))
        assert total == Decimal(0)

    async def test_query_joins_assets_and_filters_ghost_states(self):
        """Regression: phantom -19.5% on morning briefing.

        Soft-deleted, placeholder, and unconfirmed assets must be excluded
        from the historical sum so it matches ``get_user_assets`` semantics.
        We assert the SQL text itself (rather than mocking row-level
        behaviour) because the filter belongs to the query plan — that's
        what guarantees DB-side consistency under any data shape.
        """
        result = MagicMock()
        result.scalar.return_value = Decimal(0)
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        await nwc.calculate_historical(db, uuid.uuid4(), date(2026, 6, 4))

        executed_stmt = db.execute.await_args.args[0]
        sql = str(executed_stmt).lower()
        assert "join assets" in sql
        assert "a.is_active = true" in sql
        assert "a.is_placeholder_asset = false" in sql
        assert "a.is_confirmed = true" in sql
        # The join must be wired through the asset_id FK, not a cross-join.
        assert "a.id = s.asset_id" in sql

    async def test_change_excludes_sold_asset_snapshot_regression(
        self, monkeypatch
    ):
        """End-to-end shape of the bug shown in the screenshot.

        User holds 2.5 tỷ today. Yesterday a ~592.8tr stock was sold (cash
        proceeds NOT yet re-added). Pre-fix: historical summed both the
        live cash + the sold stock snapshot ⇒ previous ≈ 3.09 tỷ ⇒
        -19.5%. Post-fix: the JOIN drops the sold asset, so previous
        matches current and the briefing reports a flat change.
        """
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[_asset("cash", "VCB", 2_500_000_000)]),
        )
        # The post-fix query returns only the still-held assets'
        # snapshots, so previous == current.
        result = MagicMock()
        result.scalar.return_value = Decimal("2_500_000_000")
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        change = await nwc.calculate_change(db, uuid.uuid4(), period="day")

        assert change.current == Decimal("2_500_000_000")
        assert change.previous == Decimal("2_500_000_000")
        assert change.change_absolute == Decimal(0)
        assert change.change_percentage == 0.0


@pytest.mark.asyncio
class TestCalculateChange:
    async def test_positive_change(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[_asset("cash", "VCB", 110_000_000)]),
        )
        # Historical: 100m a week ago.
        result = MagicMock()
        result.scalar.return_value = Decimal("100_000_000")
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        change = await nwc.calculate_change(db, uuid.uuid4(), period="week")
        assert change.current == Decimal("110_000_000")
        assert change.previous == Decimal("100_000_000")
        assert change.change_absolute == Decimal("10_000_000")
        assert change.change_percentage == 10.0
        assert change.period_label == "tuần trước"

    async def test_no_history_means_zero_pct(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[_asset("cash", "VCB", 50_000_000)]),
        )
        result = MagicMock()
        result.scalar.return_value = Decimal(0)
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        change = await nwc.calculate_change(db, uuid.uuid4(), period="day")
        assert change.previous == Decimal(0)
        assert change.change_absolute == Decimal("50_000_000")
        # No baseline — display flat 0% rather than +inf%.
        assert change.change_percentage == 0.0

    async def test_change_from_current_skips_current_recalculation(self, monkeypatch):
        async def fail_calculate(*_args, **_kwargs):
            raise AssertionError("calculate() should not be called")

        monkeypatch.setattr(nwc, "calculate", fail_calculate)
        result = MagicMock()
        result.scalar.return_value = Decimal("80_000_000")
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        change = await nwc.calculate_change_from_current(
            db, uuid.uuid4(), Decimal("100_000_000"), period="month"
        )

        assert change.current == Decimal("100_000_000")
        assert change.previous == Decimal("80_000_000")
        assert change.change_absolute == Decimal("20_000_000")
        assert change.change_percentage == 25.0
        assert change.period_label == "tháng trước"
        db.execute.assert_awaited_once()

    async def test_unknown_period_raises(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[]),
        )
        db = MagicMock()
        with pytest.raises(ValueError):
            await nwc.calculate_change(db, uuid.uuid4(), period="decade")

    @pytest.mark.parametrize(
        "period,label",
        [
            ("day", "hôm qua"),
            ("week", "tuần trước"),
            ("month", "tháng trước"),
            ("year", "năm trước"),
        ],
    )
    async def test_period_labels(self, period, label, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[]),
        )
        result = MagicMock()
        result.scalar.return_value = Decimal(0)
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        change = await nwc.calculate_change(db, uuid.uuid4(), period=period)
        assert change.period_label == label


@pytest.mark.asyncio
async def test_change_vs_last_month_end_uses_calendar_anchor(monkeypatch):
    """Baseline must be the LAST day of the previous calendar month —
    not ``today - 30 days``. That alignment is the entire point of the
    helper: it keeps the headline delta consistent with the ⚖️ comparison
    surface (which also reads the end-of-month snapshot)."""
    captured: dict = {}

    async def fake_historical(_db, _uid, target_date):
        captured["target_date"] = target_date
        return Decimal("100000000")

    monkeypatch.setattr(nwc, "calculate_historical", fake_historical)
    db = MagicMock()

    today = date(2026, 6, 4)
    change = await nwc.calculate_change_vs_last_month_end_from_current(
        db, uuid.uuid4(), Decimal("110000000"), today=today
    )

    assert captured["target_date"] == date(2026, 5, 31)
    assert change.previous == Decimal("100000000")
    assert change.current == Decimal("110000000")
    assert change.change_absolute == Decimal("10000000")
    assert change.change_percentage == 10.0
    assert change.period_label == "tháng trước"


@pytest.mark.asyncio
async def test_change_vs_last_month_end_handles_zero_baseline(monkeypatch):
    """No snapshot ⇒ previous=0, pct stays 0 (never divide-by-zero)."""
    monkeypatch.setattr(
        nwc, "calculate_historical", AsyncMock(return_value=Decimal(0))
    )
    db = MagicMock()
    change = await nwc.calculate_change_vs_last_month_end_from_current(
        db, uuid.uuid4(), Decimal("5000000"), today=date(2026, 6, 4)
    )
    assert change.previous == Decimal(0)
    assert change.change_percentage == 0.0


@pytest.mark.asyncio
async def test_change_vs_last_month_end_january_rolls_back_to_december(monkeypatch):
    """Month boundary at year boundary: Jan 15 ⇒ Dec 31 prev year."""
    captured: dict = {}

    async def fake_historical(_db, _uid, target_date):
        captured["target_date"] = target_date
        return Decimal("0")

    monkeypatch.setattr(nwc, "calculate_historical", fake_historical)
    db = MagicMock()
    await nwc.calculate_change_vs_last_month_end_from_current(
        db, uuid.uuid4(), Decimal("0"), today=date(2026, 1, 15)
    )
    assert captured["target_date"] == date(2025, 12, 31)


@pytest.mark.asyncio
async def test_calculate_ytd_return_uses_jan_1_baseline(monkeypatch):
    historical = AsyncMock(return_value=Decimal("100000000"))
    monkeypatch.setattr(nwc, "calculate_historical", historical)

    db = object()
    result = await nwc.calculate_ytd_return_from_current(
        db=db,
        user_id="user-1",
        current=Decimal("125000000"),
        account_created_at=datetime(2025, 6, 1),
        today=date(2026, 5, 10),
    )

    assert result.base == Decimal("100000000")
    assert result.change_percentage == 25.0
    assert result.period_label == "YTD"
    assert result.is_join_date_fallback is False
    historical.assert_awaited_once_with(db, "user-1", date(2026, 1, 1))


@pytest.mark.asyncio
async def test_calculate_ytd_return_falls_back_to_join_date(monkeypatch):
    calls = []

    async def fake_historical(db, user_id, target_date):
        calls.append((db, user_id, target_date))
        return Decimal("50000000")

    monkeypatch.setattr(nwc, "calculate_historical", fake_historical)

    result = await nwc.calculate_ytd_return_from_current(
        db="db",
        user_id="user-1",
        current=Decimal("55000000"),
        account_created_at=datetime(2026, 3, 2),
        today=date(2026, 5, 10),
    )

    assert result.period_label == "Từ ngày tham gia"
    assert result.is_join_date_fallback is True
    assert result.change_percentage == 10.0
    assert calls == [("db", "user-1", date(2026, 3, 2))]


@pytest.mark.asyncio
async def test_calculate_ytd_return_zero_base_returns_none(monkeypatch):
    monkeypatch.setattr(
        nwc,
        "calculate_historical",
        AsyncMock(return_value=Decimal("0")),
    )

    result = await nwc.calculate_ytd_return_from_current(
        db="db",
        user_id="user-1",
        current=Decimal("55000000"),
        today=date(2026, 5, 10),
    )

    assert result.change_percentage is None
    assert result.change_absolute == Decimal("55000000")
