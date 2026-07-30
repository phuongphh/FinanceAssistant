"""Regression coverage for the Telegram Twin menu entry point."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.bot.handlers import menu_handler


@pytest.mark.asyncio
async def test_twin_root_callback_always_sends_visible_submenu(monkeypatch):
    user = SimpleNamespace(
        id="user-1",
        wealth_level="young_prof",
        get_greeting_name=lambda: "An",
    )
    send_message = AsyncMock(return_value={"ok": True})
    edit_message = AsyncMock()

    monkeypatch.setattr(menu_handler, "get_user_by_telegram_id", AsyncMock(return_value=user))
    monkeypatch.setattr(menu_handler, "answer_callback", AsyncMock())
    monkeypatch.setattr(menu_handler, "send_message", send_message)
    monkeypatch.setattr(menu_handler, "edit_message_text", edit_message)
    monkeypatch.setattr(menu_handler.analytics, "track", lambda *args, **kwargs: None)

    handled = await menu_handler.handle_menu_callback(
        AsyncMock(),
        {
            "id": "callback-1",
            "data": "menu:twin",
            "from": {"id": 12345},
            "message": {"message_id": 99, "chat": {"id": 12345}},
        },
    )

    assert handled is True
    edit_message.assert_not_awaited()
    send_message.assert_awaited_once()
    payload = send_message.await_args.kwargs
    assert payload["chat_id"] == 12345
    assert "BÉ TIỀN TƯƠNG LAI" in payload["text"]
    callbacks = [
        button["callback_data"]
        for row in payload["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert "menu:twin:view_current" in callbacks
    assert "menu:twin:life_events" in callbacks
