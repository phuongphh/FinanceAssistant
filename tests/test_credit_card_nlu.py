import uuid
from types import SimpleNamespace

import pytest

from backend.bot.handlers.message import _extract_credit_card_source


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    def __init__(self, obj):
        self.obj = obj

    async def execute(self, _stmt):
        return _FakeResult(self.obj)


@pytest.mark.asyncio
async def test_extract_credit_card_source_success():
    card = SimpleNamespace(id=uuid.uuid4())
    got = await _extract_credit_card_source(
        _FakeDB(card), uuid.uuid4(), "mình ăn tối 200k trả bằng thẻ Techcombank"
    )
    assert got == ("credit_card", str(card.id))


@pytest.mark.asyncio
async def test_extract_credit_card_source_no_match():
    got = await _extract_credit_card_source(
        _FakeDB(None), uuid.uuid4(), "mình ăn tối 200k tiền mặt"
    )
    assert got == (None, None)
