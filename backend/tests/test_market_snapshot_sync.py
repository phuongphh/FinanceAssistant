from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.jobs import market_poller
from backend.services import market_service


def _snapshot(code: str = "VNINDEX") -> SimpleNamespace:
    return SimpleNamespace(
        asset_code=code,
        snapshot_date=date(2026, 8, 11),
        asset_type="index",
        price=1776.77,
        change_1d_pct=0.42,
    )


@pytest.mark.asyncio
async def test_market_poller_saves_snapshots_in_system_database():
    db = AsyncMock()
    saved = [_snapshot()]

    class SessionContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return False

    with (
        patch.object(
            market_poller,
            "get_session_factory",
            return_value=lambda: SessionContext(),
        ),
        patch.object(
            market_poller,
            "fetch_daily_snapshot",
            AsyncMock(return_value=[{"asset_code": "VNINDEX"}]),
        ),
        patch.object(
            market_poller, "save_snapshots", AsyncMock(return_value=saved)
        ) as save,
    ):
        await market_poller.poll_market()

    save.assert_awaited_once_with(db, [{"asset_code": "VNINDEX"}])
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_market_poller_does_not_commit_when_provider_returns_no_data():
    db = AsyncMock()

    class SessionContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return False

    with (
        patch.object(
            market_poller,
            "get_session_factory",
            return_value=lambda: SessionContext(),
        ),
        patch.object(
            market_poller, "fetch_daily_snapshot", AsyncMock(return_value=[])
        ),
        patch.object(market_poller, "save_snapshots", AsyncMock()) as save,
    ):
        await market_poller.poll_market()

    save.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_market_poller_rolls_back_database_failure():
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("database unavailable")

    class SessionContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return False

    with (
        patch.object(
            market_poller,
            "get_session_factory",
            return_value=lambda: SessionContext(),
        ),
        patch.object(
            market_poller,
            "fetch_daily_snapshot",
            AsyncMock(return_value=[{"asset_code": "VNINDEX"}]),
        ),
        patch.object(
            market_poller,
            "save_snapshots",
            AsyncMock(return_value=[_snapshot()]),
        ),
    ):
        await market_poller.poll_market()

    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_vn30_uses_reference_price_when_preopen_match_price_is_zero():
    row = {
        "symbol": "FPT",
        "match_price": 0,
        # MultiIndex ("match", "reference_price") is flattened this way.
        "match_reference_price": 101.5,
        "accumulated_volume": 10,
    }
    frame = MagicMock()
    frame.__len__.return_value = 1
    frame.columns = list(row)
    frame.iterrows.return_value = [(0, row)]
    board = MagicMock(return_value=frame)
    stock = MagicMock()
    stock.trading.price_board = board
    vnstock = MagicMock()
    vnstock.stock.return_value = stock

    with patch.dict("sys.modules", {"vnstock": SimpleNamespace(Vnstock=lambda: vnstock)}):
        snapshots = await market_service._fetch_vn30_snapshots(date(2026, 8, 11))

    assert snapshots[0]["asset_code"] == "FPT"
    assert snapshots[0]["price"] == 101_500


@pytest.mark.asyncio
async def test_vn30_drops_row_when_match_and_reference_prices_are_zero():
    row = {"symbol": "FPT", "match_price": 0, "reference_price": 0}
    frame = MagicMock()
    frame.__len__.return_value = 1
    frame.columns = list(row)
    frame.iterrows.return_value = [(0, row)]
    stock = MagicMock()
    stock.trading.price_board.return_value = frame
    vnstock = MagicMock()
    vnstock.stock.return_value = stock

    with patch.dict("sys.modules", {"vnstock": SimpleNamespace(Vnstock=lambda: vnstock)}):
        snapshots = await market_service._fetch_vn30_snapshots(date(2026, 8, 11))

    assert snapshots == []
