from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import about_handler
from backend.bot.setup_commands import BOT_COMMANDS
from backend.config import APP_VERSION
from backend.workers import telegram_worker
from backend.tests.test_telegram_worker import _make_fake_session


@pytest.mark.asyncio
async def test_cmd_about_sends_versioned_about_page():
    with patch.object(about_handler, "send_message", new_callable=AsyncMock) as send:
        await about_handler.cmd_about(chat_id=123)

    send.assert_awaited_once_with(
        chat_id=123,
        text=about_handler.ABOUT_TEXT,
        parse_mode="Markdown",
        reply_markup=about_handler.ABOUT_KEYBOARD,
    )
    assert APP_VERSION in about_handler.ABOUT_TEXT
    assert "© 2026 Nui Truc AI. All rights reserved." in about_handler.ABOUT_TEXT
    assert about_handler.ABOUT_SUPPORT_EMAIL in about_handler.ABOUT_TEXT


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["/about", "/about@BeTienTestBot"])
async def test_about_command_routes_without_user_lookup(text):
    fake_session = _make_fake_session()
    factory = MagicMock(return_value=fake_session)

    with patch.object(
        telegram_worker, "get_session_factory", return_value=factory
    ), patch(
        "backend.bot.handlers.about_handler.cmd_about", new_callable=AsyncMock
    ) as cmd_about, patch(
        "backend.services.dashboard_service.get_user_by_telegram_id",
        new_callable=AsyncMock,
    ) as get_user:
        await telegram_worker.route_update(
            {"update_id": 233, "message": {"text": text, "chat": {"id": 456}}}
        )

    cmd_about.assert_awaited_once_with(456)
    get_user.assert_not_awaited()
    fake_session.commit.assert_awaited_once()


def test_about_keyboard_has_required_buttons_one_per_row():
    rows = about_handler.ABOUT_KEYBOARD["inline_keyboard"]
    assert rows == [
        [{"text": "🌐 Website Công Ty", "url": "https://nuitruc.ai"}],
        [{"text": "🔏 Chính Sách Bảo Mật", "url": "https://nuitruc.ai/privacy"}],
        [{"text": "📧 Hỗ Trợ", "callback_data": about_handler.ABOUT_SUPPORT_CALLBACK}],
    ]
    assert all(len(row) == 1 for row in rows)


def test_about_keyboard_uses_telegram_safe_urls():
    for row in about_handler.ABOUT_KEYBOARD["inline_keyboard"]:
        button = row[0]
        if "url" in button:
            assert button["url"].startswith(("https://", "http://"))


@pytest.mark.asyncio
async def test_about_support_callback_shows_support_email():
    callback_query = {"id": "cb-1", "data": about_handler.ABOUT_SUPPORT_CALLBACK}

    with patch.object(
        about_handler, "answer_callback", new_callable=AsyncMock
    ) as answer:
        handled = await about_handler.handle_about_callback(callback_query)

    assert handled is True
    answer.assert_awaited_once_with(
        "cb-1",
        text=about_handler.ABOUT_SUPPORT_ALERT,
        show_alert=True,
    )


@pytest.mark.asyncio
async def test_about_callback_ignores_other_callbacks():
    with patch.object(
        about_handler, "answer_callback", new_callable=AsyncMock
    ) as answer:
        handled = await about_handler.handle_about_callback(
            {"id": "cb-2", "data": "menu:main"}
        )

    assert handled is False
    answer.assert_not_awaited()


def test_about_command_is_in_bot_menu():
    assert {"command": "about", "description": "Thông tin ứng dụng"} in BOT_COMMANDS
