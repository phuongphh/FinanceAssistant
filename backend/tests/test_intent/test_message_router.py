"""Tests for the Phase 3.5 changes to ``backend.bot.handlers.message``.

Covers:
  - The intent callback handler resolves confirm:yes by creating a
    saving expense.
  - confirm:no clears state without writing.
  - clarify:* re-runs classification with the original raw text.
  - Plain text while a confirmation is pending nudges the user.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import free_form_text, message
from backend.intent import pending_action
from backend.intent.dispatcher import (
    DispatchOutcome,
    OUTCOME_CONFIRM_SENT,
)
from backend.intent.intents import IntentResult, IntentType


def _user(state=None) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "An"
    user.wizard_state = state
    return user


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _confirm_callback(action: str = "yes") -> dict:
    return {
        "id": "cbq-1",
        "data": f"intent_confirm:{action}",
        "message": {"chat": {"id": 999}},
        "from": {"id": 12345},
    }


def _clarify_callback(idx: int = 0) -> dict:
    return {
        "id": "cbq-1",
        "data": f"intent_clarify:{idx}",
        "message": {"chat": {"id": 999}},
        "from": {"id": 12345},
    }


@pytest.mark.asyncio
async def test_confirm_yes_creates_expense_and_clears_state():
    user = _user(
        state={
            "flow": pending_action.FLOW_PENDING_ACTION,
            "intent": IntentType.ACTION_RECORD_SAVING.value,
            "parameters": {"amount": 1_000_000},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db = _fake_db()

    expense_obj = MagicMock()
    expense_obj.id = uuid.uuid4()
    expense_obj.amount = 1_000_000

    with patch.object(
        message, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        message.expense_service,
        "create_expense",
        AsyncMock(return_value=expense_obj),
    ) as mock_create, patch.object(
        message, "send_transaction_confirmation", AsyncMock()
    ) as mock_confirm, patch.object(
        message, "send_message", AsyncMock()
    ):
        handled = await message.handle_intent_callback(db, _confirm_callback("yes"))

    assert handled is True
    mock_create.assert_awaited_once()
    mock_confirm.assert_awaited_once()
    # State cleared.
    assert user.wizard_state is None


@pytest.mark.asyncio
async def test_confirm_no_clears_state_without_writing():
    user = _user(
        state={
            "flow": pending_action.FLOW_PENDING_ACTION,
            "intent": IntentType.ACTION_RECORD_SAVING.value,
            "parameters": {"amount": 1_000_000},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db = _fake_db()
    with patch.object(
        message, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        message.expense_service, "create_expense", AsyncMock()
    ) as mock_create, patch.object(
        message, "send_message", AsyncMock()
    ):
        handled = await message.handle_intent_callback(db, _confirm_callback("no"))

    assert handled is True
    mock_create.assert_not_called()
    assert user.wizard_state is None


@pytest.mark.asyncio
async def test_confirm_callback_with_no_active_state_replies_safely():
    user = _user(state=None)
    db = _fake_db()
    with patch.object(
        message, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        message, "send_message", AsyncMock()
    ) as mock_send:
        handled = await message.handle_intent_callback(db, _confirm_callback())

    assert handled is True
    mock_send.assert_awaited_once()
    text = mock_send.call_args.args[1]
    assert "không tìm thấy" in text.lower() or "đang chờ" in text.lower()


@pytest.mark.asyncio
async def test_unknown_intent_callback_prefix_returns_false():
    db = _fake_db()
    cbq = {"data": "menu:foo", "message": {"chat": {"id": 1}}, "from": {"id": 9}}
    handled = await message.handle_intent_callback(db, cbq)
    assert handled is False


@pytest.mark.asyncio
async def test_clarify_callback_reroutes_via_classify_and_dispatch():
    user = _user(
        state={
            "flow": pending_action.FLOW_AWAITING_CLARIFY,
            "original_intent": IntentType.QUERY_ASSETS.value,
            "raw_text": "tài sản",
            "parameters": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db = _fake_db()
    with patch.object(
        message, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ), patch.object(
        free_form_text, "classify_and_dispatch", AsyncMock(return_value=None)
    ) as mock_route:
        handled = await message.handle_intent_callback(db, _clarify_callback())

    assert handled is True
    mock_route.assert_awaited_once()
    kwargs = mock_route.call_args.kwargs
    assert kwargs["text"] == "tài sản"


@pytest.mark.asyncio
async def test_pending_action_active_blocks_classification_with_nudge():
    """Free-form text while a confirm is pending should send the
    'still waiting' reminder, not start a fresh classification."""
    user = _user(
        state={
            "flow": pending_action.FLOW_PENDING_ACTION,
            "intent": IntentType.ACTION_RECORD_SAVING.value,
            "parameters": {"amount": 1_000_000},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db = _fake_db()

    pipeline_stub = MagicMock()
    pipeline_stub.classify = AsyncMock()  # should NOT be called
    pipeline_stub.llm_classifier = None
    free_form_text.set_pipeline(pipeline_stub)

    try:
        with patch.object(
            free_form_text, "send_message", AsyncMock()
        ) as mock_send:
            outcome = await free_form_text.classify_and_dispatch(
                db=db, chat_id=1, user=user, text="another thing",
            )
    finally:
        free_form_text.set_pipeline(free_form_text._pipeline)

    pipeline_stub.classify.assert_not_called()
    assert outcome is not None
    assert outcome.kind == OUTCOME_CONFIRM_SENT
    mock_send.assert_awaited_once()
