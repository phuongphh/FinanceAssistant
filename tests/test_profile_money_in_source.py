"""Tests for the ``default_money_in_source`` Profile menu handlers."""

import uuid
from types import SimpleNamespace

import pytest

from backend.profile.handlers import profile_menu


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    """Returns the same asset rows for every ``execute`` (money-in only
    queries assets — credit cards are never fetched)."""

    def __init__(self, assets):
        self._assets = assets
        self.flushed = False

    async def execute(self, _stmt):
        return _ScalarsResult(self._assets)

    async def flush(self):
        self.flushed = True


def _asset(name, subtype):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        subtype=subtype,
        asset_type="cash",
        is_active=True,
        created_at=None,
    )


@pytest.mark.asyncio
async def test_money_in_options_exclude_credit_cards():
    bank = _asset("Techcombank", "bank_account")
    wallet = _asset("Momo", "momo")
    db = FakeDB([bank, wallet])

    options = await profile_menu._money_in_source_options(uuid.uuid4(), db)

    keys = [key for key, _ in options]
    # cash is always present and first
    assert keys[0] == "cash"
    # bank + wallet present, no credit_card key anywhere
    assert f"bank_account:{bank.id}" in keys
    assert f"e_wallet:{wallet.id}" in keys
    assert not any(k.startswith("credit_card:") for k in keys)


@pytest.mark.asyncio
async def test_set_default_money_in_source_persists(monkeypatch):
    sent = []
    monkeypatch.setattr(
        profile_menu,
        "send_message",
        lambda **kw: sent.append(kw) or _noop(),
    )
    monkeypatch.setattr(
        profile_menu,
        "edit_message_text",
        lambda **kw: _noop(),
    )

    bank = _asset("Techcombank", "bank_account")
    db = FakeDB([bank])
    profile = SimpleNamespace(default_money_in_source=None)
    user = SimpleNamespace(id=uuid.uuid4())

    await profile_menu._set_default_money_in_source(
        db, 123, None, user, profile, "cash"
    )

    assert profile.default_money_in_source == "cash"
    assert db.flushed is True
    # a confirmation message was sent
    assert any("changed" in str(m.get("text", "")) or m.get("text") for m in sent)


@pytest.mark.asyncio
async def test_set_default_money_in_source_rejects_invalid(monkeypatch):
    sent = []
    monkeypatch.setattr(
        profile_menu,
        "send_message",
        lambda **kw: sent.append(kw) or _noop(),
    )
    monkeypatch.setattr(profile_menu, "edit_message_text", lambda **kw: _noop())

    db = FakeDB([])
    profile = SimpleNamespace(default_money_in_source=None)
    user = SimpleNamespace(id=uuid.uuid4())

    await profile_menu._set_default_money_in_source(
        db, 123, None, user, profile, "credit_card:" + str(uuid.uuid4())
    )

    # invalid key never persisted
    assert profile.default_money_in_source is None
    assert db.flushed is False


async def _noop():
    return None
