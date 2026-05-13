"""Expense Enhancement regression tests.

Covers the new source-resolution / warning logic and transaction-type
filtering introduced by issue #562 without requiring a real database.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.expense import Expense
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service
from backend.wealth.models.asset import Asset


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value

    def scalars(self):
        out = MagicMock()
        out.all.return_value = self._value if isinstance(self._value, list) else []
        return out


def _db(*, get_result=None, execute_results=None):
    db = MagicMock()
    db.get = AsyncMock(return_value=get_result)
    db.execute = AsyncMock(side_effect=execute_results or [])
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


def _asset(
    *,
    user_id: uuid.UUID,
    current_value: str = "1000000",
    subtype: str = "momo",
    extra: dict | None = None,
) -> Asset:
    return Asset(
        id=uuid.uuid4(),
        user_id=user_id,
        asset_type="cash",
        subtype=subtype,
        name="Nguồn tiền",
        initial_value=Decimal("0"),
        current_value=Decimal(current_value),
        acquired_at=date.today(),
        extra=extra,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_resolve_source_asset_inferrs_wallet_provider_and_warns_for_expense():
    user_id = uuid.uuid4()
    asset = _asset(user_id=user_id, current_value="50000", subtype="momo", extra=None)
    db = _db(get_result=asset)

    result = await expense_service.resolve_source_asset_for_payload(
        db,
        user_id,
        ExpenseCreate(
            amount=100_000,
            source_asset_id=asset.id,
            transaction_type="expense",
        ),
    )

    assert result.source_asset_id == asset.id
    assert result.source_type == "e_wallet"
    assert result.e_wallet_provider == "momo"
    assert result.warning == {"insufficient_balance": True, "balance": 50000.0}


@pytest.mark.asyncio
async def test_resolve_source_asset_money_in_has_no_balance_warning():
    user_id = uuid.uuid4()
    asset = _asset(user_id=user_id, current_value="-100000", subtype="cash")
    db = _db(get_result=asset)

    result = await expense_service.resolve_source_asset_for_payload(
        db,
        user_id,
        ExpenseCreate(
            amount=200_000,
            source_asset_id=asset.id,
            source_type="cash",
            transaction_type="money_in",
        ),
    )

    assert result.source_asset_id == asset.id
    assert result.source_type == "cash"
    assert result.e_wallet_provider is None
    assert result.warning is None


@pytest.mark.asyncio
async def test_get_or_create_source_asset_auto_creates_zero_balance_wallet():
    user_id = uuid.uuid4()
    db = _db(execute_results=[_ScalarResult(None)])

    asset = await expense_service.get_or_create_source_asset(
        db,
        user_id,
        source_type="e_wallet",
        e_wallet_provider="zalopay",
    )

    assert asset.user_id == user_id
    assert asset.asset_type == "cash"
    assert asset.subtype == "zalopay"
    assert asset.current_value == Decimal("0")
    assert asset.extra == {"source_type": "e_wallet", "e_wallet_provider": "zalopay"}
    db.add.assert_called_once_with(asset)
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_expenses_defaults_to_outflow_filter():
    db = _db(execute_results=[_ScalarResult([])])

    await expense_service.list_expenses(db, uuid.uuid4())

    stmt = db.execute.call_args.args[0]
    assert "expenses.transaction_type" in str(stmt)
    assert stmt.compile().params["transaction_type_1"] == "expense"


@pytest.mark.asyncio
async def test_source_asset_adjustment_locks_row_before_balance_update():
    user_id = uuid.uuid4()
    asset = _asset(user_id=user_id, current_value="500000", subtype="cash")
    expense = Expense(
        id=uuid.uuid4(),
        user_id=user_id,
        amount=Decimal("150000"),
        transaction_type="expense",
        source_asset_id=asset.id,
    )
    db = _db(execute_results=[_ScalarResult(asset)])

    await expense_service._adjust_source_asset(db, expense, multiplier=1)

    stmt = db.execute.call_args.args[0]
    assert "FOR UPDATE" in str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert asset.current_value == Decimal("350000")
