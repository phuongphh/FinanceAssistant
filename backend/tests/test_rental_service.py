"""Unit tests for ``backend.wealth.services.rental_service``.

DB-free: a fake AsyncSession captures ``add`` / ``execute`` calls and
returns canned rows. We assert:

- ``mark_as_rental`` flips flags + writes metadata + creates one
  ``IncomeStream`` row whose ``extra.source_asset_id`` matches.
- Re-marking updates the existing income stream rather than creating
  a duplicate.
- ``update_occupancy`` flips the linked stream's ``is_active`` based
  on rented/vacant.
- ``unmark_as_rental`` clears metadata + pauses the stream (does not
  delete it).
- Non-real-estate assets are rejected with ``ValueError``.
- ``get_rental_yield_summary`` aggregates correctly across multiple
  rentals (occupied + vacant), and returns ``None`` blended yield
  when there are no rentals.

The boundary contract — service flushes, never commits — is asserted
by checking ``flush.assert_awaited`` and ``commit.assert_not_awaited``
at the end of mutating tests.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.wealth.models.asset import Asset
from backend.wealth.models.income_stream import IncomeStream
from backend.wealth.schemas.rental import OccupancyStatus, RentalMetadata
from backend.wealth.services import rental_service


def _make_rental_stream(
    *,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    amount: Decimal,
    is_active: bool = True,
    name: str = "rental",
) -> IncomeStream:
    """Build an IncomeStream the way Phase 3.8 Epic 2 expects.

    Centralised so old-style ``source_type``/``amount_monthly`` kwargs
    don't proliferate through tests.
    """
    return IncomeStream(
        user_id=user_id,
        stream_type="rental",
        is_passive=True,
        name=name,
        amount=amount,
        currency="VND",
        schedule_type="monthly",
        start_date=date.today(),
        is_active=is_active,
        source_asset_id=asset_id,
        extra={rental_service.SOURCE_ASSET_ID_KEY: str(asset_id)},
    )


def _make_asset(
    *,
    user_id: uuid.UUID,
    asset_type: str = "real_estate",
    is_rental: bool = False,
    rental_metadata: dict | None = None,
    current_value: Decimal = Decimal("2_500_000_000"),
    name: str = "Nhà Mỹ Đình",
) -> Asset:
    a = Asset()
    a.id = uuid.uuid4()
    a.user_id = user_id
    a.asset_type = asset_type
    a.subtype = "house_primary" if asset_type == "real_estate" else None
    a.name = name
    a.initial_value = Decimal("2_000_000_000")
    a.current_value = current_value
    a.acquired_at = date(2020, 1, 1)
    a.last_valued_at = datetime.utcnow()
    a.extra = {}
    a.is_active = True
    a.is_rental = is_rental
    a.rental_metadata = rental_metadata
    a.created_at = datetime.utcnow()
    a.updated_at = datetime.utcnow()
    return a


def _result_with_scalar(value):
    """Mimic ``(await db.execute(stmt)).scalar_one_or_none()`` returning value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    scalars = MagicMock()
    scalars.all.return_value = value if isinstance(value, list) else (
        [value] if value is not None else []
    )
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
    db.delete = AsyncMock()
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
class TestMarkAsRental:
    async def test_marks_real_estate_and_creates_income_stream(self):
        user_id = uuid.uuid4()
        asset = _make_asset(user_id=user_id)
        # 1st execute: get_asset_by_id → asset
        # 2nd execute: _find_stream_for_asset → empty (no existing stream)
        db = _mock_session([
            _result_with_scalar(asset),
            _result_with_scalars([]),
        ])

        metadata = RentalMetadata(
            monthly_rent=Decimal("15_000_000"),
            occupancy_status=OccupancyStatus.RENTED,
            monthly_expenses=Decimal("1_500_000"),
        )
        result = await rental_service.mark_as_rental(
            db, user_id, asset.id, metadata,
        )

        assert result.is_rental is True
        # rental_metadata is JSON-serialised (Decimals → str)
        assert result.rental_metadata["monthly_rent"] == "15000000"
        assert result.rental_metadata["occupancy_status"] == "rented"
        # IncomeStream created + linked.
        added = [c.args[0] for c in db.add.call_args_list]
        streams = [x for x in added if isinstance(x, IncomeStream)]
        assert len(streams) == 1
        stream = streams[0]
        assert stream.stream_type == "rental"
        assert stream.is_passive is True
        assert stream.amount == Decimal("13_500_000")  # net
        assert stream.schedule_type == "monthly"
        assert stream.is_active is True  # rented → active
        # Phase 3.8 Epic 2: source_asset_id is now a real FK column.
        # ``extra`` keeps the snapshot for read-only consumers.
        assert stream.source_asset_id == asset.id
        assert stream.extra[rental_service.SOURCE_ASSET_ID_KEY] == str(asset.id)
        # Stream name must hold the bare asset name — the type-aware prefix
        # ("BĐS cho thuê — …") is composed at render time from
        # ``income_types.yaml`` so YAML edits propagate without a migration.
        assert stream.name == asset.name
        _assert_flush_only(db)

    async def test_non_real_estate_rejected(self):
        user_id = uuid.uuid4()
        cash = _make_asset(user_id=user_id, asset_type="cash")
        db = _mock_session([_result_with_scalar(cash)])

        with pytest.raises(ValueError, match="Only real_estate"):
            await rental_service.mark_as_rental(
                db, user_id, cash.id,
                RentalMetadata(monthly_rent=Decimal("1")),
            )

    async def test_missing_asset_raises(self):
        db = _mock_session([_result_with_scalar(None)])
        with pytest.raises(ValueError, match="not found"):
            await rental_service.mark_as_rental(
                db, uuid.uuid4(), uuid.uuid4(),
                RentalMetadata(monthly_rent=Decimal("1")),
            )

    async def test_remarking_updates_existing_stream(self):
        """Re-calling mark_as_rental on an already-rental asset should
        update the existing IncomeStream, not create a second one."""
        user_id = uuid.uuid4()
        asset = _make_asset(
            user_id=user_id,
            is_rental=True,
            rental_metadata={
                "monthly_rent": "15000000",
                "monthly_expenses": "1500000",
                "occupancy_status": "rented",
                "tenant_name": None,
                "lease_start_date": None,
                "lease_end_date": None,
                "deposit_held": "0",
            },
        )
        existing_stream = _make_rental_stream(
            user_id=user_id, asset_id=asset.id,
            amount=Decimal("13_500_000"), name="Old name",
        )
        existing_stream.extra = {
            rental_service.SOURCE_ASSET_ID_KEY: str(asset.id),
            "occupancy_status": "rented",
            "monthly_rent": "15000000",
            "monthly_expenses": "1500000",
        }
        db = _mock_session([
            _result_with_scalar(asset),
            _result_with_scalars([existing_stream]),
        ])

        new_metadata = RentalMetadata(
            monthly_rent=Decimal("16_000_000"),  # rent went up
            occupancy_status=OccupancyStatus.RENTED,
            monthly_expenses=Decimal("1_500_000"),
        )
        await rental_service.mark_as_rental(
            db, user_id, asset.id, new_metadata,
        )

        # No NEW stream added — existing was mutated.
        added = [c.args[0] for c in db.add.call_args_list]
        assert not any(isinstance(x, IncomeStream) for x in added)
        # Stream amount updated to new net = 16tr - 1.5tr.
        assert existing_stream.amount == Decimal("14_500_000")


@pytest.mark.asyncio
class TestUpdateOccupancy:
    async def test_rented_to_vacant_pauses_stream(self):
        user_id = uuid.uuid4()
        asset = _make_asset(
            user_id=user_id,
            is_rental=True,
            rental_metadata={
                "monthly_rent": "15000000",
                "monthly_expenses": "1500000",
                "occupancy_status": "rented",
                "tenant_name": "Tuấn",
                "lease_start_date": None,
                "lease_end_date": None,
                "deposit_held": "0",
            },
        )
        existing_stream = _make_rental_stream(
            user_id=user_id, asset_id=asset.id,
            amount=Decimal("13_500_000"),
        )
        db = _mock_session([
            _result_with_scalar(asset),
            _result_with_scalars([existing_stream]),
        ])

        await rental_service.update_occupancy(
            db, user_id, asset.id, OccupancyStatus.VACANT,
        )
        # Status flipped + linked stream paused.
        assert asset.rental_metadata["occupancy_status"] == "vacant"
        assert existing_stream.is_active is False

    async def test_vacant_to_rented_resumes_stream(self):
        user_id = uuid.uuid4()
        asset = _make_asset(
            user_id=user_id,
            is_rental=True,
            rental_metadata={
                "monthly_rent": "15000000",
                "monthly_expenses": "1500000",
                "occupancy_status": "vacant",
                "tenant_name": None,
                "lease_start_date": None,
                "lease_end_date": None,
                "deposit_held": "0",
            },
        )
        paused_stream = _make_rental_stream(
            user_id=user_id, asset_id=asset.id,
            amount=Decimal("13_500_000"), is_active=False,
        )
        db = _mock_session([
            _result_with_scalar(asset),
            _result_with_scalars([paused_stream]),
        ])

        await rental_service.update_occupancy(
            db, user_id, asset.id, OccupancyStatus.RENTED,
        )
        assert asset.rental_metadata["occupancy_status"] == "rented"
        assert paused_stream.is_active is True

    async def test_invalid_status_rejected(self):
        db = _mock_session()
        with pytest.raises(ValueError, match="Invalid occupancy_status"):
            await rental_service.update_occupancy(
                db, uuid.uuid4(), uuid.uuid4(), "garbage",
            )

    async def test_non_rental_asset_rejected(self):
        user_id = uuid.uuid4()
        asset = _make_asset(user_id=user_id, is_rental=False)
        db = _mock_session([_result_with_scalar(asset)])
        with pytest.raises(ValueError, match="not a rental"):
            await rental_service.update_occupancy(
                db, user_id, asset.id, OccupancyStatus.VACANT,
            )


@pytest.mark.asyncio
class TestUnmarkAsRental:
    async def test_clears_metadata_and_pauses_stream(self):
        user_id = uuid.uuid4()
        asset = _make_asset(
            user_id=user_id,
            is_rental=True,
            rental_metadata={
                "monthly_rent": "15000000",
                "monthly_expenses": "0",
                "occupancy_status": "rented",
                "tenant_name": None,
                "lease_start_date": None,
                "lease_end_date": None,
                "deposit_held": "0",
            },
        )
        existing_stream = _make_rental_stream(
            user_id=user_id, asset_id=asset.id,
            amount=Decimal("15000000"),
        )
        db = _mock_session([
            _result_with_scalar(asset),
            _result_with_scalars([existing_stream]),
        ])
        await rental_service.unmark_as_rental(db, user_id, asset.id)
        assert asset.is_rental is False
        assert asset.rental_metadata is None
        # Stream paused, NOT deleted (re-mark restores it).
        assert existing_stream.is_active is False
        db.delete.assert_not_awaited()

    async def test_already_unmarked_is_noop(self):
        user_id = uuid.uuid4()
        asset = _make_asset(user_id=user_id, is_rental=False)
        db = _mock_session([_result_with_scalar(asset)])
        result = await rental_service.unmark_as_rental(db, user_id, asset.id)
        assert result is asset
        # No flush call needed for a no-op (defensive).


@pytest.mark.asyncio
class TestPauseStreamsForAsset:
    """Public helper used by asset_service deletion + unmark_as_rental."""

    async def test_active_stream_paused_returns_true(self):
        user_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        stream = _make_rental_stream(
            user_id=user_id, asset_id=asset_id, amount=Decimal("15000000"),
        )
        db = _mock_session([_result_with_scalar(stream)])

        paused = await rental_service.pause_streams_for_asset(db, user_id, asset_id)

        assert paused is True
        assert stream.is_active is False

    async def test_no_stream_returns_false(self):
        user_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        db = _mock_session([_result_with_scalar(None)])

        paused = await rental_service.pause_streams_for_asset(db, user_id, asset_id)

        assert paused is False

    async def test_already_paused_returns_false(self):
        """No-op when stream exists but is_active is already False
        (idempotent — second delete shouldn't claim new work)."""
        user_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        stream = _make_rental_stream(
            user_id=user_id, asset_id=asset_id,
            amount=Decimal("15000000"), is_active=False,
        )
        db = _mock_session([_result_with_scalar(stream)])

        paused = await rental_service.pause_streams_for_asset(db, user_id, asset_id)

        assert paused is False
        assert stream.is_active is False


@pytest.mark.asyncio
class TestYieldSummary:
    async def test_empty_user_returns_none_blended(self):
        user_id = uuid.uuid4()
        db = _mock_session([_result_with_scalars([])])
        summary = await rental_service.get_rental_yield_summary(db, user_id)
        assert summary.property_count == 0
        assert summary.blended_annual_yield_pct is None

    async def test_aggregates_across_rentals(self):
        user_id = uuid.uuid4()
        rented = _make_asset(
            user_id=user_id, is_rental=True,
            current_value=Decimal("2_500_000_000"),
            rental_metadata={
                "monthly_rent": "15000000",
                "monthly_expenses": "1500000",
                "occupancy_status": "rented",
                "tenant_name": None,
                "lease_start_date": None,
                "lease_end_date": None,
                "deposit_held": "0",
            },
        )
        vacant = _make_asset(
            user_id=user_id, is_rental=True,
            current_value=Decimal("3_000_000_000"),
            name="Nhà Cầu Giấy",
            rental_metadata={
                "monthly_rent": "20000000",
                "monthly_expenses": "2000000",
                "occupancy_status": "vacant",
                "tenant_name": None,
                "lease_start_date": None,
                "lease_end_date": None,
                "deposit_held": "0",
            },
        )
        db = _mock_session([_result_with_scalars([rented, vacant])])

        s = await rental_service.get_rental_yield_summary(db, user_id)
        assert s.property_count == 2
        assert s.occupied_count == 1
        assert s.vacant_count == 1
        assert s.self_use_count == 0
        assert s.total_monthly_rent == Decimal("35_000_000")
        assert s.total_monthly_expenses == Decimal("3_500_000")
        assert s.net_monthly_yield == Decimal("31_500_000")
        assert s.annual_passive_income == Decimal("378_000_000")
        # Blended yield = 378tr / 5.5 tỷ × 100 ≈ 6.87%
        assert s.blended_annual_yield_pct == pytest.approx(6.872, abs=0.01)
