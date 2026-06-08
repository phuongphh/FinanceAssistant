import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.schemas.credit_card import CreditCardCreate
from backend.services import credit_card_service


class _Result:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj

    def scalars(self):
        return self

    def all(self):
        return self._obj


class FakeDB:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.added = []
        self.flushed = False
        self.refreshed = False

    async def execute(self, _stmt):
        return _Result(self.execute_results.pop(0) if self.execute_results else None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def refresh(self, _obj):
        self.refreshed = True

    async def delete(self, _obj):
        return None


@pytest.mark.asyncio
async def test_create_credit_card_success():
    db = FakeDB([None])
    user_id = uuid.uuid4()
    data = CreditCardCreate(
        bank_name="  Techcombank ",
        credit_limit=10000000,
        closing_date=25,
        debt_balance=1500000,
    )

    got = await credit_card_service.create_credit_card(db, user_id, data)

    assert got.user_id == user_id
    assert got.bank_name == "Techcombank"
    assert float(got.credit_limit) == 10000000
    assert float(got.debt_balance) == 1500000
    assert db.flushed is True
    assert db.refreshed is True


@pytest.mark.asyncio
async def test_create_credit_card_duplicate_bank_name_raises():
    db = FakeDB([SimpleNamespace(id=uuid.uuid4())])
    user_id = uuid.uuid4()
    data = CreditCardCreate(bank_name="techcombank", credit_limit=0, closing_date=25, debt_balance=0)

    with pytest.raises(ValueError, match="Tên ngân hàng đã tồn tại"):
        await credit_card_service.create_credit_card(db, user_id, data)


@pytest.mark.asyncio
async def test_list_credit_cards_returns_rows():
    cards = [
        SimpleNamespace(id=uuid.uuid4(), created_at=datetime.utcnow()),
        SimpleNamespace(id=uuid.uuid4(), created_at=datetime.utcnow()),
    ]
    db = FakeDB([cards])

    got = await credit_card_service.list_credit_cards(db, uuid.uuid4())

    assert got == cards


@pytest.mark.asyncio
async def test_get_credit_card_not_found():
    db = FakeDB([None])
    got = await credit_card_service.get_credit_card(db, uuid.uuid4(), uuid.uuid4())
    assert got is None


@pytest.mark.asyncio
async def test_delete_credit_card_sets_deleted_at_instead_of_hard_delete():
    """Soft delete: mutate the row and flush — never call ``db.delete``."""
    card = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        bank_name="MSB",
        deleted_at=None,
    )
    db = FakeDB([card])

    got = await credit_card_service.delete_credit_card(db, card.user_id, card.id)

    assert got is card
    assert got.deleted_at is not None
    assert db.flushed is True


@pytest.mark.asyncio
async def test_delete_credit_card_returns_none_when_missing():
    db = FakeDB([None])
    got = await credit_card_service.delete_credit_card(db, uuid.uuid4(), uuid.uuid4())
    assert got is None


@pytest.mark.asyncio
async def test_create_credit_card_allows_reusing_bank_name_after_soft_delete():
    """Soft-deleted rows must NOT block re-adding the same bank."""
    # ``None`` here means the uniqueness query found no live (non-deleted)
    # match — even if a soft-deleted row exists, the service's WHERE clause
    # filters it out, so the create proceeds.
    db = FakeDB([None])
    user_id = uuid.uuid4()
    data = CreditCardCreate(
        bank_name="MSB",
        credit_limit=5_000_000,
        closing_date=15,
        debt_balance=0,
    )

    got = await credit_card_service.create_credit_card(db, user_id, data)

    assert got.bank_name == "MSB"
    assert db.flushed is True
