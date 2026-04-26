"""Tests for ``backend.services.wealth_dashboard_service``.

Covers the dashboard payload composer (``build_overview``) and the
trend query (``get_trend``). Real Postgres isn't required — we
monkeypatch ``net_worth_calculator`` and ``asset_service`` and stub
``db.execute`` for the trend SQL.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import wealth_dashboard_service as svc
from backend.wealth.services import net_worth_calculator as nwc


def _asset(asset_type, name, current, initial=None, subtype=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        asset_type=asset_type,
        subtype=subtype,
        initial_value=Decimal(initial if initial is not None else current),
        current_value=Decimal(current),
        acquired_at=date(2026, 1, 1),
    )


@pytest.mark.asyncio
class TestBuildOverview:
    async def test_starter_with_one_cash_asset(self, monkeypatch):
        user_id = uuid.uuid4()

        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[_asset("cash", "VCB", 5_000_000)]),
        )

        async def fake_change(db, uid, period):
            return nwc.NetWorthChange(
                current=Decimal("5_000_000"),
                previous=Decimal("4_000_000"),
                change_absolute=Decimal("1_000_000"),
                change_percentage=25.0,
                period_label=nwc._PERIOD_LABELS[period],
            )

        monkeypatch.setattr(nwc, "calculate_change", fake_change)

        async def fake_trend(db, uid, *, days, end=None):
            return [{"date": "2026-04-01", "value": 5_000_000.0}]

        monkeypatch.setattr(svc, "get_trend", fake_trend)

        # ``calculate`` runs through nwc.calculate which already uses
        # the patched asset_service — leave it unmocked.
        db = MagicMock()

        result = await svc.build_overview(db, user_id, trend_days=90)

        assert result["net_worth"] == 5_000_000.0
        assert result["asset_count"] == 1
        assert result["level"] == "starter"
        assert result["level_label"] == "Khởi đầu"
        assert result["change_day"]["amount"] == 1_000_000.0
        assert result["change_month"]["amount"] == 1_000_000.0
        assert len(result["assets"]) == 1
        assert result["assets"][0]["asset_type"] == "cash"
        assert result["assets"][0]["icon"] == "💵"
        assert result["assets"][0]["change"] == 0.0  # initial == current
        # Breakdown labelled and percent-summed.
        assert result["breakdown"][0]["label"] == "Tiền mặt & Tài khoản"
        assert result["breakdown"][0]["pct"] == 100.0

        ms = result["next_milestone"]
        assert ms["target"] == 30_000_000.0
        assert ms["target_level"] == "young_prof"
        # 5tr / 30tr ≈ 16.67 → rounded to 2 dp.
        assert ms["pct_progress"] == pytest.approx(16.67, abs=0.01)
        assert ms["remaining"] == 25_000_000.0

    async def test_empty_user_zero_net_worth(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[]),
        )

        async def fake_change(db, uid, period):
            return nwc.NetWorthChange(
                current=Decimal(0),
                previous=Decimal(0),
                change_absolute=Decimal(0),
                change_percentage=0.0,
                period_label="",
            )

        monkeypatch.setattr(nwc, "calculate_change", fake_change)
        monkeypatch.setattr(
            svc, "get_trend",
            AsyncMock(return_value=[]),
        )

        result = await svc.build_overview(MagicMock(), uuid.uuid4(), trend_days=30)

        assert result["net_worth"] == 0.0
        assert result["asset_count"] == 0
        assert result["level"] == "starter"
        assert result["assets"] == []
        assert result["breakdown"] == []
        assert result["trend"] == []
        # User at 0₫ should still see the first milestone — Young Professional.
        assert result["next_milestone"]["target"] == 30_000_000.0
        assert result["next_milestone"]["pct_progress"] == 0.0

    async def test_breakdown_sorted_desc(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[
                _asset("cash", "VCB", 50_000_000),
                _asset("stock", "VNM", 200_000_000),
                _asset("real_estate", "Nhà MD", 1_500_000_000),
            ]),
        )

        async def fake_change(db, uid, period):
            return nwc.NetWorthChange(
                current=Decimal("1_750_000_000"),
                previous=Decimal("1_750_000_000"),
                change_absolute=Decimal(0),
                change_percentage=0.0,
                period_label="",
            )

        monkeypatch.setattr(nwc, "calculate_change", fake_change)
        monkeypatch.setattr(svc, "get_trend", AsyncMock(return_value=[]))

        result = await svc.build_overview(MagicMock(), uuid.uuid4())

        types = [b["asset_type"] for b in result["breakdown"]]
        assert types == ["real_estate", "stock", "cash"]
        # Largest band is HNW → next_milestone goes to next billion.
        assert result["level"] == "hnw"
        assert result["next_milestone"]["target"] == 2_000_000_000.0


@pytest.mark.asyncio
class TestGetTrend:
    async def test_rejects_invalid_days(self):
        with pytest.raises(ValueError):
            await svc.get_trend(MagicMock(), uuid.uuid4(), days=7)

    async def test_returns_serialized_rows(self):
        rows = [
            SimpleNamespace(day=date(2026, 4, 1), total=Decimal("1_000_000")),
            SimpleNamespace(day=date(2026, 4, 2), total=Decimal("1_500_000")),
            SimpleNamespace(day=date(2026, 4, 3), total=None),
        ]
        result = MagicMock()
        result.all.return_value = rows
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        out = await svc.get_trend(db, uuid.uuid4(), days=30)
        assert out == [
            {"date": "2026-04-01", "value": 1_000_000.0},
            {"date": "2026-04-02", "value": 1_500_000.0},
            {"date": "2026-04-03", "value": 0.0},
        ]
