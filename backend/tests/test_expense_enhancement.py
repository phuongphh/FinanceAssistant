"""Expense Enhancement regression tests.

Covers the new source-resolution / warning logic and transaction-type
filtering introduced by issue #562 without requiring a real database.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
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
async def test_resolve_source_asset_rejects_non_wallet_subtype_for_e_wallet_source():
    """PR #948 P2 fix: if the caller pins ``source_type=e_wallet`` to an
    asset whose ``subtype`` is anything other than a wallet provider (or
    the generic ``e_wallet`` subtype), the resolver MUST reject it.
    Otherwise we'd silently persist a mismatched source — the dashboard
    would render the wrong label and the source resolver would pick up
    a bogus subtype downstream."""
    user_id = uuid.uuid4()
    bank_asset = _asset(
        user_id=user_id,
        current_value="500000",
        subtype="bank_checking",
    )
    db = _db(get_result=bank_asset)

    with pytest.raises(ValueError):
        await expense_service.resolve_source_asset_for_payload(
            db,
            user_id,
            ExpenseCreate(
                amount=100_000,
                source_asset_id=bank_asset.id,
                source_type="e_wallet",
                transaction_type="expense",
            ),
        )


@pytest.mark.asyncio
async def test_resolve_source_asset_accepts_generic_e_wallet_subtype():
    """Wallet assets created by the cash wizard carry the generic
    ``subtype='e_wallet'`` (no provider hint). These are valid e_wallet
    sources — the resolver must let them through without inferring a
    bogus provider."""
    user_id = uuid.uuid4()
    wallet = _asset(
        user_id=user_id,
        current_value="200000",
        subtype="e_wallet",
    )
    db = _db(get_result=wallet)

    result = await expense_service.resolve_source_asset_for_payload(
        db,
        user_id,
        ExpenseCreate(
            amount=100_000,
            source_asset_id=wallet.id,
            source_type="e_wallet",
            transaction_type="expense",
        ),
    )

    assert result.source_asset_id == wallet.id
    assert result.source_type == "e_wallet"
    # Generic-subtype wallet has no provider hint — must not fabricate one.
    assert result.e_wallet_provider is None


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
async def test_get_or_create_source_asset_prefers_funded_cash_over_old_empty_row():
    user_id = uuid.uuid4()
    old_auto = _asset(user_id=user_id, current_value="0", subtype="cash")
    old_auto.name = "Tiền mặt tự tạo"
    old_auto.is_confirmed = True
    old_auto.is_placeholder_asset = False
    old_auto.created_at = datetime(2026, 1, 1)
    funded_cash = _asset(user_id=user_id, current_value="1000000000", subtype="cash")
    funded_cash.name = "Tiền mặt"
    funded_cash.is_confirmed = True
    funded_cash.is_placeholder_asset = False
    funded_cash.created_at = datetime(2026, 2, 1)
    db = _db(execute_results=[_ScalarResult([old_auto, funded_cash])])

    asset = await expense_service.get_or_create_source_asset(
        db,
        user_id,
        source_type="cash",
        amount=Decimal("2000000"),
    )

    assert asset.id == funded_cash.id
    assert asset.current_value == Decimal("1000000000")
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_source_asset_cash_spend_has_no_false_warning_with_funded_cash():
    user_id = uuid.uuid4()
    old_auto = _asset(user_id=user_id, current_value="0", subtype="cash")
    old_auto.created_at = datetime(2026, 1, 1)
    funded_cash = _asset(user_id=user_id, current_value="1000000000", subtype="cash")
    funded_cash.created_at = datetime(2026, 2, 1)
    db = _db(execute_results=[_ScalarResult([old_auto, funded_cash])])

    result = await expense_service.resolve_source_asset_for_payload(
        db,
        user_id,
        ExpenseCreate(
            amount=2_000_000,
            source_type="cash",
            transaction_type="expense",
        ),
    )

    assert result.source_asset_id == funded_cash.id
    assert result.source_type == "cash"
    assert result.warning is None


@pytest.mark.asyncio
async def test_get_or_create_source_asset_maps_bank_account_to_checking_asset():
    user_id = uuid.uuid4()
    checking = _asset(
        user_id=user_id,
        current_value="5000000",
        subtype="bank_checking",
    )
    db = _db(execute_results=[_ScalarResult([checking])])

    asset = await expense_service.get_or_create_source_asset(
        db,
        user_id,
        source_type="bank_account",
        amount=Decimal("2000000"),
    )

    assert asset.id == checking.id
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_source_asset_maps_provider_to_generic_wallet_asset():
    user_id = uuid.uuid4()
    wallet = _asset(
        user_id=user_id,
        current_value="3000000",
        subtype="e_wallet",
    )
    wallet.name = "MoMo"
    db = _db(execute_results=[_ScalarResult([wallet])])

    asset = await expense_service.get_or_create_source_asset(
        db,
        user_id,
        source_type="e_wallet",
        e_wallet_provider="momo",
        amount=Decimal("2000000"),
    )

    assert asset.id == wallet.id
    db.add.assert_not_called()


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
