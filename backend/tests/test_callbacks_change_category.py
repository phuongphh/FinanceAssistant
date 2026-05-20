from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.bot.handlers import callbacks


@pytest.mark.asyncio
async def test_change_category_rejects_invalid_category(monkeypatch):
    expense = SimpleNamespace(id="tx-1", category="food")

    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    answer_callback = AsyncMock()
    monkeypatch.setattr(callbacks, "answer_callback", answer_callback)
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", AsyncMock())
    analytics_track = Mock()
    monkeypatch.setattr(callbacks.analytics, "track", analytics_track)

    db = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
    user = SimpleNamespace(id=99)

    await callbacks._handle_change_category(
        db=db,
        user=user,
        args=["tx-1", "__invalid__"],
        callback_id="cb1",
        chat_id=1,
        message_id=10,
    )

    assert expense.category == "food"
    db.flush.assert_not_awaited()
    db.refresh.assert_not_awaited()
    analytics_track.assert_not_called()
    answer_callback.assert_awaited_once()
    assert answer_callback.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_change_category_accepts_valid_category(monkeypatch):
    expense = SimpleNamespace(id="tx-1", category="food")

    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())
    rerender = AsyncMock()
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", rerender)
    analytics_track = Mock()
    monkeypatch.setattr(callbacks.analytics, "track", analytics_track)

    db = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
    user = SimpleNamespace(id=99)

    await callbacks._handle_change_category(
        db=db,
        user=user,
        args=["tx-1", "shopping"],
        callback_id="cb1",
        chat_id=1,
        message_id=10,
    )

    assert expense.category == "shopping"
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once_with(expense)
    rerender.assert_awaited_once_with(1, 10, expense)
    analytics_track.assert_called_once()
