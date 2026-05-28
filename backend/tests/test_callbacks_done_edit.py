"""Issue #897 — ✅ Đồng ý strips the inline keyboard."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.bot.handlers import callbacks


@pytest.mark.asyncio
async def test_done_edit_strips_keyboard(monkeypatch):
    edit_markup = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    answer = AsyncMock()
    monkeypatch.setattr(callbacks, "answer_callback", answer)

    await callbacks._handle_done_edit(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=["tx-1"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    edit_markup.assert_awaited_once()
    kwargs = edit_markup.await_args.kwargs
    assert kwargs["chat_id"] == 10
    assert kwargs["message_id"] == 20
    assert kwargs["reply_markup"] == {"inline_keyboard": []}
    answer.assert_awaited_once()
