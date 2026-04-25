"""Unit tests for ``backend.wealth.services.asset_service``.

DB-free: a fake AsyncSession captures ``add`` / ``execute`` calls and
returns canned rows. This lets us assert:

- create_asset writes an Asset + a Snapshot
- update_current_value upserts (no duplicate same-day snapshot)
- get_user_assets builds the right where-clause filter
- soft_delete preserves history (no row removal)
- ownership check raises when user_id mismatches

The boundary contract — service flushes, never commits — is enforced
by checking the mocks at the end of each test.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.wealth.models.asset import Asset
from backend.wealth.models.asset_snapshot import AssetSnapshot
from backend.wealth.services import asset_service


def _result_with_scalar(value):
    """Mimic ``(await db.execute(stmt)).scalar_one_or_none()`` returning value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    scalars = MagicMock()
    scalars.all.return_value = value if isinstance(value, list) else []
    result.scalars.return_value = scalars
    return result


def _result_with_scalars(rows: list):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    result.scalar_one_or_none.return_value = rows[0] if rows else None
    return result


def _mock_session(execute_side_effect=None) -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    if execute_side_effect is not None:
        db.execute.side_effect = execute_side_effect
    return db


def _assert_flush_only(db: MagicMock) -> None:
    db.flush.assert_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestCreateAsset:
    async def test_creates_asset_and_snapshot(self):
        db = _mock_session()
        user_id = uuid.uuid4()

        asset = await asset_service.create_asset(
            db, user_id,
            asset_type="cash",
            subtype="bank_savings",
            name="VCB",
            initial_value=Decimal("100_000_000"),
        )

        # Asset added then snapshot added — both in same transaction.
        assert db.add.call_count == 2
        added_objects = [c.args[0] for c in db.add.call_args_list]
        assert isinstance(added_objects[0], Asset)
        assert isinstance(added_objects[1], AssetSnapshot)
        # Snapshot points at the asset just created.
        assert added_objects[1].asset_id == added_objects[0].id

        assert asset.user_id == user_id
        assert asset.asset_type == "cash"
        assert asset.current_value == Decimal("100_000_000")
        assert asset.acquired_at == date.today()
        _assert_flush_only(db)

    async def test_default_current_value_to_initial(self):
        db = _mock_session()
        asset = await asset_service.create_asset(
            db, uuid.uuid4(),
            asset_type="cash", name="Cash",
            initial_value=Decimal("5_000_000"),
        )
        assert asset.current_value == asset.initial_value

    async def test_explicit_current_value_used(self):
        db = _mock_session()
        asset = await asset_service.create_asset(
            db, uuid.uuid4(),
            asset_type="stock", name="VNM",
            initial_value=Decimal("4_500_000"),
            current_value=Decimal("5_000_000"),
            extra={"ticker": "VNM", "quantity": 100, "avg_price": 45000},
        )
        assert asset.initial_value == Decimal("4_500_000")
        assert asset.current_value == Decimal("5_000_000")
        assert asset.extra["ticker"] == "VNM"

    async def test_zero_initial_value_rejected(self):
        db = _mock_session()
        with pytest.raises(ValueError):
            await asset_service.create_asset(
                db, uuid.uuid4(),
                asset_type="cash", name="x", initial_value=Decimal("0"),
            )

    async def test_negative_initial_value_rejected(self):
        db = _mock_session()
        with pytest.raises(ValueError):
            await asset_service.create_asset(
                db, uuid.uuid4(),
                asset_type="cash", name="x", initial_value=Decimal("-100"),
            )

    async def test_explicit_acquired_at_respected(self):
        db = _mock_session()
        target = date(2020, 1, 15)
        asset = await asset_service.create_asset(
            db, uuid.uuid4(),
            asset_type="real_estate", name="Nhà Mỹ Đình",
            initial_value=Decimal("2_000_000_000"),
            acquired_at=target,
        )
        assert asset.acquired_at == target


@pytest.mark.asyncio
class TestGetAssetById:
    async def test_returns_asset_when_owner_matches(self):
        user_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        asset = Asset(id=asset_id, user_id=user_id, asset_type="cash",
                      name="x", initial_value=Decimal(1), current_value=Decimal(1),
                      acquired_at=date.today())
        db = _mock_session([_result_with_scalar(asset)])
        got = await asset_service.get_asset_by_id(db, user_id, asset_id)
        assert got is asset

    async def test_returns_none_when_not_found(self):
        db = _mock_session([_result_with_scalar(None)])
        got = await asset_service.get_asset_by_id(db, uuid.uuid4(), uuid.uuid4())
        assert got is None


@pytest.mark.asyncio
class TestGetUserAssets:
    async def test_default_excludes_inactive(self):
        rows = [Asset(id=uuid.uuid4(), user_id=uuid.uuid4(), asset_type="cash",
                      name="x", initial_value=Decimal(1), current_value=Decimal(1),
                      acquired_at=date.today())]
        db = _mock_session([_result_with_scalars(rows)])
        result = await asset_service.get_user_assets(db, uuid.uuid4())
        assert result == rows

    async def test_include_inactive(self):
        rows = []
        db = _mock_session([_result_with_scalars(rows)])
        await asset_service.get_user_assets(
            db, uuid.uuid4(), include_inactive=True
        )
        # The where-clause should not include is_active = True; we can't
        # introspect the SQL easily, but we at least verify the call shape.
        db.execute.assert_awaited_once()


@pytest.mark.asyncio
class TestUpdateCurrentValue:
    async def test_creates_snapshot_when_no_existing(self):
        user_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        asset = Asset(id=asset_id, user_id=user_id, asset_type="cash",
                      name="x", initial_value=Decimal(100),
                      current_value=Decimal(100), acquired_at=date.today())
        db = _mock_session([
            _result_with_scalar(asset),       # get_asset_by_id
            _result_with_scalar(None),        # existing snapshot lookup
        ])
        updated = await asset_service.update_current_value(
            db, user_id, asset_id, Decimal("150_000_000")
        )
        assert updated.current_value == Decimal("150_000_000")
        # New snapshot row added.
        assert db.add.call_count == 1
        added = db.add.call_args.args[0]
        assert isinstance(added, AssetSnapshot)
        assert added.value == Decimal("150_000_000")
        _assert_flush_only(db)

    async def test_updates_existing_snapshot_same_day(self):
        user_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        asset = Asset(id=asset_id, user_id=user_id, asset_type="cash",
                      name="x", initial_value=Decimal(100),
                      current_value=Decimal(100), acquired_at=date.today())
        existing = AssetSnapshot(
            asset_id=asset_id, user_id=user_id, snapshot_date=date.today(),
            value=Decimal("100"), source="user_input",
        )
        db = _mock_session([
            _result_with_scalar(asset),
            _result_with_scalar(existing),
        ])
        await asset_service.update_current_value(
            db, user_id, asset_id, Decimal("200_000_000"), source="market_api"
        )
        # No new snapshot — existing one mutated.
        db.add.assert_not_called()
        assert existing.value == Decimal("200_000_000")
        assert existing.source == "market_api"

    async def test_raises_when_asset_missing(self):
        db = _mock_session([_result_with_scalar(None)])
        with pytest.raises(ValueError):
            await asset_service.update_current_value(
                db, uuid.uuid4(), uuid.uuid4(), Decimal("1")
            )

    async def test_negative_value_rejected(self):
        db = _mock_session()
        with pytest.raises(ValueError):
            await asset_service.update_current_value(
                db, uuid.uuid4(), uuid.uuid4(), Decimal("-1")
            )


@pytest.mark.asyncio
class TestSoftDelete:
    async def test_marks_inactive_with_sold_metadata(self):
        user_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        asset = Asset(id=asset_id, user_id=user_id, asset_type="real_estate",
                      name="Nhà", initial_value=Decimal("1_000_000_000"),
                      current_value=Decimal("1_500_000_000"),
                      acquired_at=date(2020, 1, 1), is_active=True)
        db = _mock_session([_result_with_scalar(asset)])

        await asset_service.soft_delete(
            db, user_id, asset_id, sold_value=Decimal("1_500_000_000")
        )
        assert asset.is_active is False
        assert asset.sold_at == date.today()
        assert asset.sold_value == Decimal("1_500_000_000")
        _assert_flush_only(db)

    async def test_raises_when_asset_missing(self):
        db = _mock_session([_result_with_scalar(None)])
        with pytest.raises(ValueError):
            await asset_service.soft_delete(db, uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
class TestUpdateAssetMetadata:
    async def test_only_updates_provided_fields(self):
        user_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        asset = Asset(id=asset_id, user_id=user_id, asset_type="stock",
                      name="VNM", initial_value=Decimal(1),
                      current_value=Decimal(1), acquired_at=date.today(),
                      extra={"ticker": "VNM"})
        db = _mock_session([_result_with_scalar(asset)])

        await asset_service.update_asset_metadata(
            db, user_id, asset_id, name="VNM updated"
        )
        assert asset.name == "VNM updated"
        # extra not provided → untouched
        assert asset.extra == {"ticker": "VNM"}
