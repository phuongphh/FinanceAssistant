"""GetAssetsTool unit tests.

DB-free: a fake AsyncSession returns a canned list of Asset rows so
the tool's filter/sort/limit logic is exercised in isolation. The
critical winners-only test (the bug the entire phase exists to fix)
lives here."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent.tools.get_assets import GetAssetsTool
from backend.agent.tools.schemas import (
    AssetFilter,
    GetAssetsInput,
    NumericFilter,
    SortOrder,
)
from backend.wealth.models.asset import Asset


def _make_asset(
    *,
    name: str,
    asset_type: str = "stock",
    current_value: Decimal,
    initial_value: Decimal,
    ticker: str | None = None,
    quantity: float | None = None,
) -> Asset:
    """Build an Asset detached from a session — pure data carrier."""
    extra: dict = {}
    if ticker:
        extra["ticker"] = ticker
    if quantity is not None:
        extra["quantity"] = quantity
    a = Asset(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        asset_type=asset_type,
        name=name,
        initial_value=Decimal(initial_value),
        current_value=Decimal(current_value),
        acquired_at=date.today(),
        last_valued_at=datetime.utcnow(),
        extra=extra,
        is_active=True,
    )
    return a


def _mixed_portfolio() -> list[Asset]:
    """The canonical fixture mirroring the bug report:
    VNM +10%, HPG -5%, NVDA +20%, FPT -3%."""
    return [
        _make_asset(name="VNM", ticker="VNM",
                    current_value=Decimal("110_000_000"),
                    initial_value=Decimal("100_000_000")),
        _make_asset(name="HPG", ticker="HPG",
                    current_value=Decimal("95_000_000"),
                    initial_value=Decimal("100_000_000")),
        _make_asset(name="NVDA", ticker="NVDA",
                    current_value=Decimal("120_000_000"),
                    initial_value=Decimal("100_000_000")),
        _make_asset(name="FPT", ticker="FPT",
                    current_value=Decimal("97_000_000"),
                    initial_value=Decimal("100_000_000")),
    ]


def _mock_db_returning(rows: list[Asset]) -> MagicMock:
    """``execute(stmt).scalars().all() == rows``."""
    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    return db


def _user() -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.display_name = "Hà"
    return u


@pytest.mark.asyncio
class TestWinnersOnly:
    """THE critical bug — Phase 3.5 returned ALL stocks, not just winners."""

    async def test_winners_filter_excludes_losers(self):
        db = _mock_db_returning(_mixed_portfolio())
        tool = GetAssetsTool()

        out = await tool.execute(
            GetAssetsInput(
                filter=AssetFilter(
                    asset_type="stock", gain_pct=NumericFilter(gt=0)
                )
            ),
            _user(),
            db,
        )

        names = {a.name for a in out.assets}
        assert "VNM" in names
        assert "NVDA" in names
        # The bug: these MUST NOT appear.
        assert "HPG" not in names
        assert "FPT" not in names
        assert out.count == 2
        assert all(a.gain_pct is not None and a.gain_pct > 0 for a in out.assets)


@pytest.mark.asyncio
class TestFilters:
    async def test_losers_filter(self):
        tool = GetAssetsTool()
        db = _mock_db_returning(_mixed_portfolio())
        out = await tool.execute(
            GetAssetsInput(
                filter=AssetFilter(
                    asset_type="stock", gain_pct=NumericFilter(lt=0)
                )
            ),
            _user(),
            db,
        )
        names = {a.name for a in out.assets}
        assert names == {"HPG", "FPT"}

    async def test_value_threshold(self):
        tool = GetAssetsTool()
        db = _mock_db_returning(_mixed_portfolio())
        out = await tool.execute(
            GetAssetsInput(
                filter=AssetFilter(value=NumericFilter(gt=100_000_000))
            ),
            _user(),
            db,
        )
        # Only VNM (110M) and NVDA (120M) above 100M.
        names = {a.name for a in out.assets}
        assert names == {"VNM", "NVDA"}

    async def test_ticker_filter_case_insensitive(self):
        tool = GetAssetsTool()
        db = _mock_db_returning(_mixed_portfolio())
        out = await tool.execute(
            GetAssetsInput(filter=AssetFilter(ticker=["vnm"])),
            _user(),
            db,
        )
        assert out.count == 1
        assert out.assets[0].name == "VNM"

    async def test_asset_with_zero_initial_excluded_from_pct_filter(self):
        """Assets without a cost basis have no gain_pct; they shouldn't
        sneak through a winners filter."""
        rows = _mixed_portfolio()
        rows.append(
            _make_asset(
                name="LegacyCash",
                asset_type="cash",
                current_value=Decimal("50_000_000"),
                initial_value=Decimal("0"),
            )
        )
        tool = GetAssetsTool()
        db = _mock_db_returning(rows)
        out = await tool.execute(
            GetAssetsInput(
                filter=AssetFilter(gain_pct=NumericFilter(gt=0))
            ),
            _user(),
            db,
        )
        assert "LegacyCash" not in {a.name for a in out.assets}


@pytest.mark.asyncio
class TestSort:
    async def test_value_desc(self):
        tool = GetAssetsTool()
        db = _mock_db_returning(_mixed_portfolio())
        out = await tool.execute(
            GetAssetsInput(sort=SortOrder.VALUE_DESC),
            _user(),
            db,
        )
        names = [a.name for a in out.assets]
        assert names == ["NVDA", "VNM", "FPT", "HPG"]

    async def test_gain_pct_desc_with_limit(self):
        tool = GetAssetsTool()
        db = _mock_db_returning(_mixed_portfolio())
        out = await tool.execute(
            GetAssetsInput(sort=SortOrder.GAIN_PCT_DESC, limit=2),
            _user(),
            db,
        )
        names = [a.name for a in out.assets]
        assert names == ["NVDA", "VNM"]

    async def test_gain_pct_asc(self):
        tool = GetAssetsTool()
        db = _mock_db_returning(_mixed_portfolio())
        out = await tool.execute(
            GetAssetsInput(sort=SortOrder.GAIN_PCT_ASC),
            _user(),
            db,
        )
        names = [a.name for a in out.assets]
        # HPG -5% worst, then FPT -3%, then VNM +10%, then NVDA +20%.
        assert names == ["HPG", "FPT", "VNM", "NVDA"]

    async def test_name_sort(self):
        tool = GetAssetsTool()
        db = _mock_db_returning(_mixed_portfolio())
        out = await tool.execute(
            GetAssetsInput(sort=SortOrder.NAME),
            _user(),
            db,
        )
        names = [a.name for a in out.assets]
        assert names == sorted(names)


@pytest.mark.asyncio
class TestEmptyAndEdges:
    async def test_empty_user(self):
        tool = GetAssetsTool()
        db = _mock_db_returning([])
        out = await tool.execute(GetAssetsInput(), _user(), db)
        assert out.count == 0
        assert out.total_value == Decimal(0)

    async def test_total_value_sums_filtered(self):
        tool = GetAssetsTool()
        db = _mock_db_returning(_mixed_portfolio())
        out = await tool.execute(
            GetAssetsInput(
                filter=AssetFilter(gain_pct=NumericFilter(gt=0))
            ),
            _user(),
            db,
        )
        assert out.total_value == Decimal("110_000_000") + Decimal("120_000_000")
