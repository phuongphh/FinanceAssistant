"""Unit tests for ``backend.wealth.services.income_service``.

DB-free with a fake AsyncSession (same pattern as ``test_rental_service``
and ``test_asset_service``). We assert:

- ``create_income_stream`` derives ``is_passive`` from YAML default
  when not overridden, defaults ``start_date`` to today, persists
  raw amount + schedule_type without normalisation.
- ``update_income_stream`` overlays only ``exclude_unset`` fields.
- ``pause_stream`` / ``resume_stream`` flip ``is_active``.
- ``get_active_streams`` filters by stream_type / is_passive.
- ``get_income_breakdown`` returns correct active/passive split +
  per-type breakdown across mixed schedules. Critical test from spec:
  salary 30tr/month + dividend 10tr/year → total ≈ 30.83tr/month.

The boundary contract — service flushes, never commits — is asserted
by ``flush.assert_awaited`` + ``commit.assert_not_awaited``.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.wealth.income_types import ScheduleType, StreamType
from backend.wealth.models.income_stream import IncomeStream
from backend.wealth.schemas.income import (
    IncomeStreamCreate,
    IncomeStreamUpdate,
)
from backend.wealth.services import income_service


def _make_stream(
    *,
    user_id: uuid.UUID,
    stream_type: str = "salary",
    is_passive: bool = False,
    amount: Decimal = Decimal("10000000"),
    schedule_type: str = "monthly",
    is_active: bool = True,
    name: str = "Test stream",
) -> IncomeStream:
    s = IncomeStream()
    s.id = uuid.uuid4()
    s.user_id = user_id
    s.stream_type = stream_type
    s.is_passive = is_passive
    s.name = name
    s.amount = amount
    s.currency = "VND"
    s.schedule_type = schedule_type
    s.start_date = date.today()
    s.is_active = is_active
    return s


def _result_with_scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    scalars = MagicMock()
    scalars.all.return_value = []
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
class TestCreateIncomeStream:
    async def test_basic_salary(self):
        user_id = uuid.uuid4()
        db = _mock_session()
        payload = IncomeStreamCreate(
            name="Lương Tech",
            stream_type=StreamType.SALARY,
            amount=Decimal("30000000"),
            schedule_type=ScheduleType.MONTHLY,
            schedule_day=5,
        )
        result = await income_service.create_income_stream(
            db, user_id, payload,
        )
        assert result.stream_type == "salary"
        # YAML default for salary is is_passive=false; the service
        # uses that when the caller doesn't override.
        assert result.is_passive is False
        assert result.amount == Decimal("30000000")
        assert result.schedule_type == "monthly"
        assert result.schedule_day == 5
        assert result.start_date == date.today()
        assert result.is_active is True
        added = [c.args[0] for c in db.add.call_args_list]
        assert any(isinstance(x, IncomeStream) for x in added)
        _assert_flush_only(db)

    async def test_dividend_defaults_to_passive(self):
        db = _mock_session()
        payload = IncomeStreamCreate(
            name="Cổ tức VNM",
            stream_type=StreamType.DIVIDEND,
            amount=Decimal("10000000"),
            schedule_type=ScheduleType.ANNUALLY,
            schedule_month=6,
        )
        result = await income_service.create_income_stream(
            db, uuid.uuid4(), payload,
        )
        assert result.is_passive is True

    async def test_explicit_passive_override(self):
        db = _mock_session()
        payload = IncomeStreamCreate(
            name="Lương lạ",
            stream_type=StreamType.SALARY,
            amount=Decimal("5000000"),
            schedule_type=ScheduleType.MONTHLY,
            is_passive=True,
        )
        result = await income_service.create_income_stream(
            db, uuid.uuid4(), payload,
        )
        assert result.is_passive is True


@pytest.mark.asyncio
class TestUpdateIncomeStream:
    async def test_partial_update_only_changes_provided_fields(self):
        user_id = uuid.uuid4()
        stream = _make_stream(user_id=user_id, amount=Decimal("30000000"))
        db = _mock_session([_result_with_scalar(stream)])

        await income_service.update_income_stream(
            db, user_id, stream.id,
            IncomeStreamUpdate(amount=Decimal("32000000")),
        )
        assert stream.amount == Decimal("32000000")
        # Other fields untouched.
        assert stream.name == "Test stream"
        assert stream.schedule_type == "monthly"
        _assert_flush_only(db)

    async def test_missing_stream_raises(self):
        db = _mock_session([_result_with_scalar(None)])
        with pytest.raises(ValueError, match="not found"):
            await income_service.update_income_stream(
                db, uuid.uuid4(), uuid.uuid4(),
                IncomeStreamUpdate(amount=Decimal(1)),
            )


@pytest.mark.asyncio
class TestPauseResumeDelete:
    async def test_pause_flips_is_active(self):
        user_id = uuid.uuid4()
        stream = _make_stream(user_id=user_id, is_active=True)
        db = _mock_session([_result_with_scalar(stream)])
        await income_service.pause_stream(db, user_id, stream.id)
        assert stream.is_active is False

    async def test_resume_flips_back(self):
        user_id = uuid.uuid4()
        stream = _make_stream(user_id=user_id, is_active=False)
        db = _mock_session([_result_with_scalar(stream)])
        await income_service.resume_stream(db, user_id, stream.id)
        assert stream.is_active is True

    async def test_delete_returns_true_on_success(self):
        user_id = uuid.uuid4()
        stream = _make_stream(user_id=user_id)
        db = _mock_session([_result_with_scalar(stream)])
        ok = await income_service.delete_stream(db, user_id, stream.id)
        assert ok is True
        db.delete.assert_awaited_once_with(stream)

    async def test_delete_returns_false_when_not_found(self):
        db = _mock_session([_result_with_scalar(None)])
        ok = await income_service.delete_stream(
            db, uuid.uuid4(), uuid.uuid4(),
        )
        assert ok is False
        db.delete.assert_not_awaited()


@pytest.mark.asyncio
class TestIncomeBreakdown:
    async def test_critical_spec_query_salary_plus_annual_dividend(self):
        """Spec § P3.8-S4 acceptance:
            User has salary 30tr/month + dividend 10tr/year →
            total monthly = 30tr + (10/12)tr ≈ 30.83tr.
        """
        user_id = uuid.uuid4()
        salary = _make_stream(
            user_id=user_id, stream_type="salary", is_passive=False,
            amount=Decimal("30000000"), schedule_type="monthly",
            name="Lương",
        )
        dividend = _make_stream(
            user_id=user_id, stream_type="dividend", is_passive=True,
            amount=Decimal("10000000"), schedule_type="annually",
            name="Cổ tức",
        )
        db = _mock_session([_result_with_scalars([salary, dividend])])

        result = await income_service.get_income_breakdown(db, user_id)
        expected_total = Decimal("30000000") + Decimal("10000000") / Decimal(12)
        assert result.total_monthly == expected_total
        assert result.active_income == Decimal("30000000")
        assert result.passive_income == Decimal("10000000") / Decimal(12)
        # Passive ratio ≈ 2.7%.
        assert result.passive_ratio == pytest.approx(2.7, abs=0.1)
        assert result.stream_count == 2
        assert "salary" in result.breakdown_by_type
        assert "dividend" in result.breakdown_by_type

    async def test_empty_user_returns_none_passive_ratio(self):
        """Distinguish "no streams" from a literal 0% passive."""
        db = _mock_session([_result_with_scalars([])])
        result = await income_service.get_income_breakdown(db, uuid.uuid4())
        assert result.total_monthly == Decimal(0)
        assert result.passive_ratio is None
        assert result.stream_count == 0

    async def test_quarterly_dividend_normalised_correctly(self):
        user_id = uuid.uuid4()
        quarterly = _make_stream(
            user_id=user_id, stream_type="dividend", is_passive=True,
            amount=Decimal("9000000"), schedule_type="quarterly",
        )
        db = _mock_session([_result_with_scalars([quarterly])])
        result = await income_service.get_income_breakdown(db, user_id)
        assert result.total_monthly == Decimal("3000000")


@pytest.mark.asyncio
class TestGetActiveStreams:
    async def test_filter_by_stream_type(self):
        user_id = uuid.uuid4()
        rental = _make_stream(user_id=user_id, stream_type="rental")
        db = _mock_session([_result_with_scalars([rental])])
        result = await income_service.get_active_streams(
            db, user_id, stream_type="rental",
        )
        assert len(result) == 1
        assert result[0].stream_type == "rental"

    async def test_filter_by_passive_only(self):
        user_id = uuid.uuid4()
        passive = _make_stream(
            user_id=user_id, stream_type="dividend", is_passive=True,
        )
        db = _mock_session([_result_with_scalars([passive])])
        result = await income_service.get_active_streams(
            db, user_id, is_passive=True,
        )
        assert len(result) == 1
        assert result[0].is_passive is True
