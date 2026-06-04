"""Tests for the ``default_money_in_source`` resolver behaviour.

Mirrors the expense-source resolver but for incoming money: applying the
profile default, rejecting credit-card sources, no-op guards, and the
confirmation-card label (with the "(mặc định)" suffix).
"""

import uuid
from types import SimpleNamespace

import pytest

from backend.schemas.expense import ExpenseCreate
from backend.services.expense_source_resolver import (
    DEFAULT_MONEY_IN_SOURCE_RAW_DATA_KEY,
    DEFAULT_SOURCE_RAW_DATA_KEY,
    DEFAULT_SOURCE_SUFFIX,
    apply_default_source,
    resolve_source_label_for_expense,
)


class FakeDB:
    """Minimal async DB stub backed by an id→object map for ``.get``."""

    def __init__(self, objects: dict | None = None):
        # keyed by primary-key value (uuid); model type ignored for simplicity
        self._objects = dict(objects or {})

    async def get(self, _model, pk):
        return self._objects.get(pk)


def _profile(*, expense=None, money_in=None):
    return SimpleNamespace(
        default_expense_source=expense,
        default_money_in_source=money_in,
    )


def _money_in_create(**overrides) -> ExpenseCreate:
    base = dict(
        amount=100000.0,
        merchant="Lương",
        source="manual",
        category="other",
        transaction_type="money_in",
    )
    base.update(overrides)
    return ExpenseCreate(**base)


# --------------------------------------------------------------------------
# apply_default_source — money_in
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_default_money_in_cash():
    user_id = uuid.uuid4()
    db = FakeDB({user_id: _profile(money_in="cash")})

    result = await apply_default_source(db, user_id, _money_in_create())

    assert result.source_type == "cash"
    assert result.source_asset_id is None
    assert result.source_credit_card_id is None
    assert result.raw_data[DEFAULT_MONEY_IN_SOURCE_RAW_DATA_KEY] is True
    # must not be tagged as the expense default
    assert DEFAULT_SOURCE_RAW_DATA_KEY not in result.raw_data


@pytest.mark.asyncio
async def test_apply_default_money_in_bank_account():
    user_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    db = FakeDB({user_id: _profile(money_in=f"bank_account:{asset_id}")})

    result = await apply_default_source(db, user_id, _money_in_create())

    assert result.source_type == "bank_account"
    assert result.source_asset_id == asset_id
    assert result.source_credit_card_id is None


@pytest.mark.asyncio
async def test_apply_default_money_in_e_wallet():
    user_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    db = FakeDB({user_id: _profile(money_in=f"e_wallet:{asset_id}")})

    result = await apply_default_source(db, user_id, _money_in_create())

    assert result.source_type == "e_wallet"
    assert result.source_asset_id == asset_id


@pytest.mark.asyncio
async def test_apply_default_money_in_rejects_credit_card():
    """A stale credit_card key must never produce money-in-from-credit."""
    user_id = uuid.uuid4()
    card_id = uuid.uuid4()
    db = FakeDB({user_id: _profile(money_in=f"credit_card:{card_id}")})

    result = await apply_default_source(db, user_id, _money_in_create())

    assert result.source_type is None
    assert result.source_credit_card_id is None
    assert result.raw_data is None


@pytest.mark.asyncio
async def test_apply_default_money_in_no_default_is_noop():
    user_id = uuid.uuid4()
    db = FakeDB({user_id: _profile(money_in=None, expense="cash")})

    result = await apply_default_source(db, user_id, _money_in_create())

    # expense default must not leak into a money-in transaction
    assert result.source_type is None


@pytest.mark.asyncio
async def test_apply_default_money_in_explicit_source_wins():
    user_id = uuid.uuid4()
    explicit_asset = uuid.uuid4()
    db = FakeDB({user_id: _profile(money_in="cash")})

    data = _money_in_create(source_type="e_wallet", source_asset_id=explicit_asset)
    result = await apply_default_source(db, user_id, data)

    assert result.source_type == "e_wallet"
    assert result.source_asset_id == explicit_asset


@pytest.mark.asyncio
async def test_apply_default_money_in_no_profile_is_noop():
    user_id = uuid.uuid4()
    db = FakeDB({})  # profile missing

    result = await apply_default_source(db, user_id, _money_in_create())

    assert result.source_type is None


@pytest.mark.asyncio
async def test_apply_default_unknown_type_is_noop():
    user_id = uuid.uuid4()
    db = FakeDB({user_id: _profile(money_in="cash", expense="cash")})

    data = ExpenseCreate(
        amount=1000.0,
        merchant="x",
        source="manual",
        category="other",
        transaction_type="expense",
    )
    # sanity: expense path still works through the same function
    result = await apply_default_source(db, user_id, data)
    assert result.source_type == "cash"
    assert result.raw_data[DEFAULT_SOURCE_RAW_DATA_KEY] is True


# --------------------------------------------------------------------------
# resolve_source_label_for_expense — money_in
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_label_money_in_cash_with_default_suffix():
    db = FakeDB({})
    expense = SimpleNamespace(
        transaction_type="money_in",
        source_type="cash",
        source_asset_id=None,
        source_credit_card_id=None,
        user_id=uuid.uuid4(),
        raw_data={DEFAULT_MONEY_IN_SOURCE_RAW_DATA_KEY: True},
    )

    label = await resolve_source_label_for_expense(db, expense)

    assert label == f"Tiền mặt{DEFAULT_SOURCE_SUFFIX}"


@pytest.mark.asyncio
async def test_resolve_label_money_in_bank_with_asset_name():
    user_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    asset = SimpleNamespace(name="Techcombank", user_id=user_id)
    db = FakeDB({asset_id: asset})
    expense = SimpleNamespace(
        transaction_type="money_in",
        source_type="bank_account",
        source_asset_id=asset_id,
        source_credit_card_id=None,
        user_id=user_id,
        raw_data={},
    )

    label = await resolve_source_label_for_expense(db, expense)

    assert label == "Tài khoản thanh toán [Techcombank]"


@pytest.mark.asyncio
async def test_resolve_label_money_in_no_source_returns_none():
    db = FakeDB({})
    expense = SimpleNamespace(
        transaction_type="money_in",
        source_type=None,
        source_asset_id=None,
        source_credit_card_id=None,
        user_id=uuid.uuid4(),
        raw_data={},
    )

    assert await resolve_source_label_for_expense(db, expense) is None
