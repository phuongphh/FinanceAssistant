"""Unit tests for ``_fetch_vn30_snapshots``.

The helper parses a pandas DataFrame returned by ``vnstock``'s
``trading.price_board``. Column names and units have shifted between
vnstock releases (snake_case ``match_price`` vs Vietnamese ``Giá khớp``,
prices in VND vs prices in thousands), so the parser probes candidate
column names and applies small unit-scaling heuristics. These tests pin
down the parser against:

* the modern snake_case schema (price already in VND × 1000 form),
* the legacy Vietnamese column schema,
* the empty DataFrame case,
* the ImportError fallback when vnstock is not installed.
"""
from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.services import market_service


def _install_fake_vnstock(monkeypatch, df) -> MagicMock:
    """Install a fake ``vnstock`` module that returns ``df`` from price_board."""
    trading = SimpleNamespace(price_board=MagicMock(return_value=df))
    stock_obj = SimpleNamespace(trading=trading)
    vs_instance = SimpleNamespace(stock=MagicMock(return_value=stock_obj))
    Vnstock = MagicMock(return_value=vs_instance)
    fake_module = SimpleNamespace(Vnstock=Vnstock)
    monkeypatch.setitem(sys.modules, "vnstock", fake_module)
    return Vnstock


@pytest.mark.asyncio
async def test_vn30_snapshots_modern_schema(monkeypatch):
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        [
            {
                "symbol": "VCB",
                "match_price": 90.5,  # thousands → scaled ×1000
                "accumulated_volume": 1_500_000,
                "accumulated_value": 135_750_000_000,  # already VND
                "change_pct": 1.2,
                "change": 1.1,
            },
            {
                "symbol": "FPT",
                "match_price": 123_500,  # already VND
                "accumulated_volume": 800_000,
                "accumulated_value": 98_800_000_000,
                "change_pct": -0.5,
                "change": -0.6,
            },
        ]
    )
    _install_fake_vnstock(monkeypatch, df)

    rows = await market_service._fetch_vn30_snapshots(date(2026, 5, 12))

    assert len(rows) == 2
    vcb = next(r for r in rows if r["asset_code"] == "VCB")
    assert vcb["price"] == pytest.approx(90_500.0)
    assert vcb["change_1d_pct"] == 1.2
    assert vcb["asset_type"] == "stock"
    assert vcb["extra_data"]["group"] == "VN30"
    assert vcb["extra_data"]["volume"] == 1_500_000.0
    assert vcb["extra_data"]["trading_value"] == 135_750_000_000.0
    assert vcb["snapshot_date"] == date(2026, 5, 12)

    fpt = next(r for r in rows if r["asset_code"] == "FPT")
    assert fpt["price"] == pytest.approx(123_500.0)
    assert fpt["change_1d_pct"] == -0.5


@pytest.mark.asyncio
async def test_vn30_snapshots_vietnamese_column_names(monkeypatch):
    """Older vnstock builds returned Vietnamese headers; the probe handles both."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        [
            {
                "Mã CP": "hpg",  # lowercased — parser uppercases
                "Giá khớp": 28.0,
                "Tổng KL": 5_000_000,
                "Tổng GT": 140_000_000_000,
                "%": 2.5,
                "Thay đổi": 0.7,
            }
        ]
    )
    _install_fake_vnstock(monkeypatch, df)

    rows = await market_service._fetch_vn30_snapshots(date(2026, 5, 12))

    assert len(rows) == 1
    assert rows[0]["asset_code"] == "HPG"
    assert rows[0]["price"] == pytest.approx(28_000.0)
    assert rows[0]["change_1d_pct"] == 2.5
    assert rows[0]["extra_data"]["volume"] == 5_000_000.0


@pytest.mark.asyncio
async def test_vn30_snapshots_skips_rows_missing_price_or_symbol(monkeypatch):
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        [
            {"symbol": "VCB", "match_price": 90.5},  # valid
            {"symbol": "BID", "match_price": None},  # dropped: no price
            {"symbol": None, "match_price": 30.0},  # dropped: no symbol
        ]
    )
    _install_fake_vnstock(monkeypatch, df)

    rows = await market_service._fetch_vn30_snapshots(date(2026, 5, 12))
    assert [r["asset_code"] for r in rows] == ["VCB"]


@pytest.mark.asyncio
async def test_vn30_snapshots_empty_dataframe(monkeypatch):
    pd = pytest.importorskip("pandas")
    _install_fake_vnstock(monkeypatch, pd.DataFrame())

    rows = await market_service._fetch_vn30_snapshots(date(2026, 5, 12))
    assert rows == []


@pytest.mark.asyncio
async def test_vn30_snapshots_returns_empty_when_vnstock_missing(monkeypatch):
    """Production fallback: if vnstock isn't installed, return [] not raise."""
    # Make ``import vnstock`` raise ImportError inside the thread.
    monkeypatch.setitem(sys.modules, "vnstock", None)

    rows = await market_service._fetch_vn30_snapshots(date(2026, 5, 12))
    assert rows == []
