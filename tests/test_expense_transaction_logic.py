import uuid
from datetime import datetime
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


@pytest.mark.asyncio
async def test_adjust_source_asset_credit_card_increases_debt():
    card = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), debt_balance=100000)
    expense = SimpleNamespace(
        user_id=card.user_id,
        source_type="credit_card",
        source_credit_card_id=card.id,
        amount=250000,
        source_asset_id=None,
    )
    db = FakeDB()

    async def _get(_model, _id):
        return card

    db.get = _get
    await expense_service._adjust_source_asset(db, expense, multiplier=1)
    assert float(card.debt_balance) == 350000


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
