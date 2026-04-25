"""Unit tests for ``backend.wealth.services.net_worth_calculator``.

We mock ``asset_service.get_user_assets`` (sync-replace via monkeypatch)
and ``db.execute`` so we can exercise the breakdown / historical /
change paths without a real Postgres.
"""
from __future__ import annotations

import uuid
from datetime import date
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
            AsyncMock(return_value=[
                _asset("cash", "VCB", 50_000_000),
                _asset("cash", "MoMo", 5_000_000),
                _asset("stock", "VNM", 20_000_000),
                _asset("real_estate", "Nhà Mỹ Đình", 2_000_000_000),
            ]),
        )
        b = await nwc.calculate(MagicMock(), uuid.uuid4())
        assert b.total == Decimal("2_075_000_000")
        assert b.asset_count == 4
        assert b.by_type["cash"] == Decimal("55_000_000")
        assert b.by_type["stock"] == Decimal("20_000_000")
        assert b.by_type["real_estate"] == Decimal("2_000_000_000")
        assert b.largest_asset == ("Nhà Mỹ Đình", Decimal("2_000_000_000"))


@pytest.mark.asyncio
class TestCalculateHistorical:
    async def test_returns_sum_from_query(self):
        result = MagicMock()
        result.scalar.return_value = Decimal("123_000_000")
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        total = await nwc.calculate_historical(
            db, uuid.uuid4(), date(2026, 4, 1)
        )
        assert total == Decimal("123_000_000")

    async def test_no_snapshots_returns_zero(self):
        result = MagicMock()
        result.scalar.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        total = await nwc.calculate_historical(
            db, uuid.uuid4(), date(2026, 4, 1)
        )
        assert total == Decimal(0)


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
