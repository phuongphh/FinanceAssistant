"""Unit tests for the wizard state service.

DB-free; uses a MagicMock AsyncSession. Verifies the layer contract
(flush only, never commit) and the JSONB shape we stash on
``users.wizard_state``.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.user import User
from backend.services import wizard_service


def _user(state: dict | None = None) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 100
    u.wizard_state = state
    return u


def _db(user: User | None) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_start_flow_writes_full_shape():
    user = _user()
    db = _db(user)
    state = await wizard_service.start_flow(
        db, user.id, "asset_add_cash", "subtype", {"asset_type": "cash"}
    )
    assert state == {
        "flow": "asset_add_cash",
        "step": "subtype",
        "draft": {"asset_type": "cash"},
    }
    assert user.wizard_state == state
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_step_merges_draft():
    user = _user({
        "flow": "asset_add_cash",
        "step": "subtype",
        "draft": {"asset_type": "cash"},
    })
    db = _db(user)
    state = await wizard_service.update_step(
        db, user.id, "amount", {"subtype": "bank_savings"}
    )
    assert state["step"] == "amount"
    assert state["draft"] == {"asset_type": "cash", "subtype": "bank_savings"}
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_step_noop_when_no_state():
    user = _user(None)
    db = _db(user)
    result = await wizard_service.update_step(db, user.id, "amount")
    assert result is None
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_resets_state():
    user = _user({"flow": "asset_add_cash", "step": "amount", "draft": {}})
    db = _db(user)
    await wizard_service.clear(db, user.id)
    assert user.wizard_state is None
    db.flush.assert_awaited_once()


def test_helpers_safe_for_none():
    assert wizard_service.get_flow(None) is None
    assert wizard_service.get_step(None) is None
    assert wizard_service.get_draft(None) == {}


def test_helpers_extract_fields():
    state = {"flow": "x", "step": "y", "draft": {"a": 1}}
    assert wizard_service.get_flow(state) == "x"
    assert wizard_service.get_step(state) == "y"
    assert wizard_service.get_draft(state) == {"a": 1}
