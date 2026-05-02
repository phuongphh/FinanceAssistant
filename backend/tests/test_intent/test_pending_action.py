"""Tests for the wizard-state-backed pending-action store."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.intent import pending_action


def _user(state: dict | None = None) -> MagicMock:
    user = MagicMock()
    user.wizard_state = state
    return user


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_set_pending_action_writes_state_and_flushes():
    user = _user(None)
    db = _fake_db()
    await pending_action.set_pending_action(
        db, user,
        intent="action_record_saving",
        parameters={"amount": 1_000_000},
    )
    assert user.wizard_state is not None
    assert user.wizard_state["flow"] == pending_action.FLOW_PENDING_ACTION
    assert user.wizard_state["intent"] == "action_record_saving"
    assert user.wizard_state["parameters"] == {"amount": 1_000_000}
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_awaiting_clarification_persists_original_text():
    user = _user(None)
    db = _fake_db()
    await pending_action.set_awaiting_clarification(
        db, user,
        intent="query_assets",
        raw_text="tài sản",
        parameters={},
    )
    assert user.wizard_state["flow"] == pending_action.FLOW_AWAITING_CLARIFY
    assert user.wizard_state["raw_text"] == "tài sản"


@pytest.mark.asyncio
async def test_clear_drops_only_intent_state():
    """clear() must NOT drop wizard_state when it belongs to another
    flow (asset-entry, storytelling)."""
    user = _user({"flow": "asset_add_cash", "step": "amount"})
    db = _fake_db()
    await pending_action.clear(db, user)
    assert user.wizard_state == {"flow": "asset_add_cash", "step": "amount"}
    db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_clear_clears_intent_state():
    user = _user(
        {
            "flow": pending_action.FLOW_PENDING_ACTION,
            "intent": "action_record_saving",
            "parameters": {"amount": 1_000_000},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db = _fake_db()
    await pending_action.clear(db, user)
    assert user.wizard_state is None
    db.flush.assert_awaited_once()


def test_get_active_returns_none_for_other_flow():
    user = _user({"flow": "asset_add_cash"})
    assert pending_action.get_active(user) is None


def test_get_active_returns_none_for_expired_state():
    stale = (
        datetime.now(timezone.utc)
        - timedelta(seconds=pending_action.CLARIFY_TTL_SECONDS + 60)
    ).isoformat()
    user = _user(
        {
            "flow": pending_action.FLOW_PENDING_ACTION,
            "created_at": stale,
        }
    )
    assert pending_action.get_active(user) is None


def test_get_active_returns_state_within_ttl():
    fresh = datetime.now(timezone.utc).isoformat()
    state = {
        "flow": pending_action.FLOW_AWAITING_CLARIFY,
        "created_at": fresh,
        "original_intent": "query_assets",
    }
    user = _user(state)
    assert pending_action.get_active(user) == state


@pytest.mark.asyncio
async def test_clear_if_expired_clears_only_when_stale():
    fresh = datetime.now(timezone.utc).isoformat()
    user = _user(
        {
            "flow": pending_action.FLOW_PENDING_ACTION,
            "created_at": fresh,
        }
    )
    db = _fake_db()
    cleared = await pending_action.clear_if_expired(db, user)
    assert cleared is False
    assert user.wizard_state is not None


@pytest.mark.asyncio
async def test_clear_if_expired_clears_stale_state():
    stale = (
        datetime.now(timezone.utc)
        - timedelta(seconds=pending_action.CLARIFY_TTL_SECONDS + 60)
    ).isoformat()
    user = _user(
        {
            "flow": pending_action.FLOW_PENDING_ACTION,
            "created_at": stale,
        }
    )
    db = _fake_db()
    cleared = await pending_action.clear_if_expired(db, user)
    assert cleared is True
    assert user.wizard_state is None


def test_clarify_ttl_matches_acceptance_criteria():
    # Issue #121: timeout = 10 minutes.
    assert pending_action.CLARIFY_TTL_SECONDS == 600
