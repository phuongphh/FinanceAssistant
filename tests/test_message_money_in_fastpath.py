"""Tests for the money-in fast-path in message handling.

``_record_transaction_with_default`` creates a money-in transaction with
the user's ``default_money_in_source`` and sends the rich confirmation,
returning False (falling back to the picker) when no default is set.
"""

import uuid
from types import SimpleNamespace

import pytest

from backend.bot.handlers import message as message_handler


@pytest.mark.asyncio
async def test_record_money_in_with_default_creates_and_confirms(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    captured = {}

    async def fake_apply_default(_db, _uid, data):
        # simulate default applied → source resolved
        return data.model_copy(update={"source_type": "cash"})

    async def fake_create(_db, _uid, data):
        created = SimpleNamespace(
            transaction_type=data.transaction_type, source_type=data.source_type
        )
        captured["created"] = created
        return created

    async def fake_confirm(_db, expense):
        captured["confirmed"] = expense

    monkeypatch.setattr(message_handler, "apply_default_source", fake_apply_default)
    monkeypatch.setattr(
        message_handler.expense_service, "create_expense", fake_create
    )
    monkeypatch.setattr(
        message_handler, "send_transaction_confirmation", fake_confirm
    )

    parsed = {"amount": 5_000_000, "transaction_type": "money_in", "note": "Lương"}
    ok = await message_handler._record_transaction_with_default(None, user, parsed)

    assert ok is True
    assert captured["created"].transaction_type == "money_in"
    assert captured["created"].source_type == "cash"
    assert captured["confirmed"] is captured["created"]


@pytest.mark.asyncio
async def test_record_money_in_without_default_returns_false(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())

    async def fake_apply_default(_db, _uid, data):
        # no default configured → source stays unresolved
        return data

    created = False

    async def fake_create(_db, _uid, data):
        nonlocal created
        created = True
        return SimpleNamespace()

    monkeypatch.setattr(message_handler, "apply_default_source", fake_apply_default)
    monkeypatch.setattr(
        message_handler.expense_service, "create_expense", fake_create
    )

    parsed = {"amount": 5_000_000, "transaction_type": "money_in"}
    ok = await message_handler._record_transaction_with_default(None, user, parsed)

    assert ok is False
    assert created is False  # never reached the create call
