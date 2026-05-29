import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services import expense_service


class _Result:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class FakeDB:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.flushed = False
        self.refreshed = False

    async def execute(self, _stmt):
        return _Result(self.execute_results.pop(0) if self.execute_results else None)

    async def flush(self):
        self.flushed = True

    async def refresh(self, _obj):
        self.refreshed = True

    async def get(self, _model, _id):
        return None


def _make_card(debt="100000"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        debt_balance=Decimal(debt),
        updated_at=None,
    )


def _make_asset(user_id, value="1000000"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        current_value=Decimal(value),
        last_valued_at=None,
    )


def _expense_on_card(card, *, amount, transaction_type):
    return SimpleNamespace(
        user_id=card.user_id,
        source_type="credit_card",
        source_credit_card_id=card.id,
        source_asset_id=None,
        amount=amount,
        transaction_type=transaction_type,
    )


def _expense_on_asset(asset, *, source_type, amount, transaction_type):
    return SimpleNamespace(
        user_id=asset.user_id,
        source_type=source_type,
        source_credit_card_id=None,
        source_asset_id=asset.id,
        amount=amount,
        transaction_type=transaction_type,
    )


@pytest.mark.asyncio
async def test_latest_active_transaction_returns_latest_match():
    tx = SimpleNamespace(id=uuid.uuid4(), status="active", created_at=datetime.utcnow())
    db = FakeDB([tx])

    got = await expense_service._latest_active_transaction(db, uuid.uuid4())

    assert got is tx


@pytest.mark.asyncio
async def test_delete_expense_marks_transaction_reversed(monkeypatch):
    expense = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), source="cash", deleted_at=None)
    tx = SimpleNamespace(status="active", reversed_at=None)
    db = FakeDB([tx])

    async def _get_expense(_db, _uid, _eid):
        return expense

    async def _adjust(*_args, **_kwargs):
        return None

    monkeypatch.setattr(expense_service, "get_expense", _get_expense)
    monkeypatch.setattr(expense_service, "_adjust_source_asset", _adjust)
    monkeypatch.setattr(expense_service.analytics, "track", lambda *a, **k: None)

    ok = await expense_service.delete_expense(db, expense.user_id, expense.id)

    assert ok is True
    assert expense.deleted_at is not None
    assert tx.status == "reversed"
    assert tx.reversed_at is not None
    assert db.flushed is True


@pytest.mark.asyncio
async def test_update_expense_marks_old_tx_edited_and_creates_new(monkeypatch):
    expense = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        amount=10000,
        transaction_type="expense",
        source="cash",
        source_asset_id=None,
        source_type="cash",
        e_wallet_provider=None,
        raw_data=None,
        expense_date=datetime.utcnow().date(),
        category="food",
        currency="VND",
        merchant="a",
        note="a",
        needs_review=False,
        month_key="2026-05",
    )
    old_tx = SimpleNamespace(id=uuid.uuid4(), status="active", edited_at=None)
    db = FakeDB([old_tx])

    async def _get_expense(_db, _uid, _eid):
        return expense

    async def _adjust(*_args, **_kwargs):
        return None

    created = {}

    async def _create(_db, _uid, _expense, **kwargs):
        created.update(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(expense_service, "get_expense", _get_expense)
    monkeypatch.setattr(expense_service, "_adjust_source_asset", _adjust)
    monkeypatch.setattr(expense_service, "_create_transaction_record", _create)

    payload = expense_service.ExpenseUpdate(note="updated")
    got = await expense_service.update_expense(db, expense.user_id, expense.id, payload)

    assert got is expense
    assert old_tx.status == "edited"
    assert old_tx.edited_at is not None
    assert created.get("original_transaction_id") == old_tx.id
    assert created.get("edited_at") is not None


# ---------------------------------------------------------------------------
# Credit-card debt adjustments — direction must be honoured.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adjust_credit_card_expense_increases_debt():
    """An expense charged to a credit card raises the debt balance."""
    card = _make_card("100000")
    expense = _expense_on_card(card, amount=250000, transaction_type="expense")
    db = FakeDB([card])

    await expense_service._adjust_source_asset(db, expense, multiplier=1)

    assert card.debt_balance == Decimal("350000")
    assert card.updated_at is not None


@pytest.mark.asyncio
async def test_adjust_credit_card_money_in_decreases_debt():
    """A money_in (refund/repayment) on a credit card lowers the debt.

    This is the regression guard for the original bug, where money_in
    wrongly *increased* the debt because direction was ignored.
    """
    card = _make_card("500000")
    expense = _expense_on_card(card, amount=200000, transaction_type="money_in")
    db = FakeDB([card])

    await expense_service._adjust_source_asset(db, expense, multiplier=1)

    assert card.debt_balance == Decimal("300000")


@pytest.mark.asyncio
async def test_adjust_credit_card_expense_reverse_restores_debt():
    """Reversing an expense (multiplier=-1) undoes the debt increase."""
    card = _make_card("350000")
    expense = _expense_on_card(card, amount=250000, transaction_type="expense")
    db = FakeDB([card])

    await expense_service._adjust_source_asset(db, expense, multiplier=-1)

    assert card.debt_balance == Decimal("100000")


@pytest.mark.asyncio
async def test_adjust_credit_card_money_in_reverse_restores_debt():
    card = _make_card("300000")
    expense = _expense_on_card(card, amount=200000, transaction_type="money_in")
    db = FakeDB([card])

    await expense_service._adjust_source_asset(db, expense, multiplier=-1)

    assert card.debt_balance == Decimal("500000")


@pytest.mark.asyncio
async def test_adjust_credit_card_skips_other_user():
    """A card owned by a different user must not be mutated."""
    card = _make_card("100000")
    expense = _expense_on_card(card, amount=250000, transaction_type="expense")
    expense.user_id = uuid.uuid4()  # different owner
    # The owner-scoped SELECT returns nothing → no card row.
    db = FakeDB([None])

    await expense_service._adjust_source_asset(db, expense, multiplier=1)

    assert card.debt_balance == Decimal("100000")


# ---------------------------------------------------------------------------
# Asset-backed sources (cash / bank_account / e_wallet) — balance moves with
# direction: expense lowers the balance, money_in raises it.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source_type", ["cash", "bank_account", "e_wallet"])
@pytest.mark.asyncio
async def test_adjust_asset_expense_decreases_balance(source_type):
    user_id = uuid.uuid4()
    asset = _make_asset(user_id, "1000000")
    expense = _expense_on_asset(
        asset, source_type=source_type, amount=300000, transaction_type="expense"
    )
    db = FakeDB([asset])

    await expense_service._adjust_source_asset(db, expense, multiplier=1)

    assert asset.current_value == Decimal("700000")
    assert asset.last_valued_at is not None


@pytest.mark.parametrize("source_type", ["cash", "bank_account", "e_wallet"])
@pytest.mark.asyncio
async def test_adjust_asset_money_in_increases_balance(source_type):
    user_id = uuid.uuid4()
    asset = _make_asset(user_id, "1000000")
    expense = _expense_on_asset(
        asset, source_type=source_type, amount=300000, transaction_type="money_in"
    )
    db = FakeDB([asset])

    await expense_service._adjust_source_asset(db, expense, multiplier=1)

    assert asset.current_value == Decimal("1300000")


@pytest.mark.parametrize("source_type", ["cash", "bank_account", "e_wallet"])
@pytest.mark.asyncio
async def test_adjust_asset_expense_reverse_restores_balance(source_type):
    user_id = uuid.uuid4()
    asset = _make_asset(user_id, "700000")
    expense = _expense_on_asset(
        asset, source_type=source_type, amount=300000, transaction_type="expense"
    )
    db = FakeDB([asset])

    await expense_service._adjust_source_asset(db, expense, multiplier=-1)

    assert asset.current_value == Decimal("1000000")


# ---------------------------------------------------------------------------
# Edit flow that switches the funding source AND changes the amount in one go.
# The double-entry (reverse old source, then apply new source) must refund the
# original amount to the OLD asset and debit the NEW amount from the NEW asset.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_expense_switch_ewallet_to_bank_with_amount_change(monkeypatch):
    """Edit a 300k e-wallet expense into a 500k bank-account expense.

    Expected: the e-wallet is refunded the *original* 300k (reverse of an
    expense adds the amount back) and the bank account is debited the *new*
    500k. Both run through the same asset branch of ``_adjust_source_asset``.
    """
    user_id = uuid.uuid4()
    ewallet_asset = _make_asset(user_id, "1000000")
    bank_asset = _make_asset(user_id, "5000000")

    expense = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        amount=300000,
        transaction_type="expense",
        source="manual",
        source_asset_id=ewallet_asset.id,
        source_credit_card_id=None,
        source_type="e_wallet",
        e_wallet_provider="momo",
        raw_data=None,
        expense_date=datetime.utcnow().date(),
        category="food_drink",
        currency="VND",
        merchant="cafe",
        note="n",
        needs_review=False,
        month_key="2026-05",
    )

    async def _get_expense(_db, _uid, _eid):
        return expense

    async def _resolve(_db, _uid, _data):
        # Mirror the resolver picking the requested bank asset for the new source.
        return expense_service.SourceResolution(
            bank_asset.id, None, None, "bank_account", None
        )

    async def _latest(_db, _eid):
        return None

    async def _create(_db, _uid, _expense, **kwargs):
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(expense_service, "get_expense", _get_expense)
    monkeypatch.setattr(expense_service, "resolve_source_asset_for_payload", _resolve)
    monkeypatch.setattr(expense_service, "_latest_active_transaction", _latest)
    monkeypatch.setattr(expense_service, "_create_transaction_record", _create)

    # execute() queue order: (1) reverse on OLD e-wallet, (2) apply on NEW bank.
    db = FakeDB([ewallet_asset, bank_asset])

    payload = expense_service.ExpenseUpdate(
        amount=500000, source_type="bank_account", source_asset_id=bank_asset.id
    )
    got = await expense_service.update_expense(db, user_id, expense.id, payload)

    assert got is expense
    # OLD e-wallet refunded the ORIGINAL amount: 1,000,000 + 300,000.
    assert ewallet_asset.current_value == Decimal("1300000")
    # NEW bank account debited the NEW amount: 5,000,000 − 500,000.
    assert bank_asset.current_value == Decimal("4500000")
    # Expense itself now points at the new source/amount.
    assert expense.source_asset_id == bank_asset.id
    assert expense.source_type == "bank_account"
    assert expense.amount == 500000


@pytest.mark.asyncio
async def test_resolve_source_asset_for_payload_credit_card_invalid_owner(monkeypatch):
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    card_id = uuid.uuid4()
    db = FakeDB()
    db.get = lambda _model, _id: None

    async def _get(_model, _id):
        return SimpleNamespace(id=card_id, user_id=other_user_id)

    db.get = _get
    payload = expense_service.ExpenseCreate(
        amount=100000,
        source="manual",
        source_type="credit_card",
        source_credit_card_id=card_id,
    )
    with pytest.raises(ValueError, match="source_credit_card_id không hợp lệ"):
        await expense_service.resolve_source_asset_for_payload(db, user_id, payload)
