"""Tests for telegram_service — Telegram API transport layer."""
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.telegram_service import (
    answer_callback,
    handle_menu_callback,
    register_bot_commands,
    send_menu,
    send_message,
    send_telegram,
)


@pytest.fixture
def mock_settings():
    with patch("backend.services.telegram_service.settings") as mock:
        mock.telegram_bot_token = "test-token-123"
        yield mock


@pytest.fixture
def mock_httpx():
    # send_telegram() now reuses a singleton AsyncClient (see the asset-wizard
    # latency fix). Patch the getter directly so each test gets a fresh mock
    # without leaking the singleton across tests.
    import backend.services.telegram_service as ts

    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": True}
    mock_response.text = '{"ok": true}'
    mock_client.post.return_value = mock_response
    mock_client.get.return_value = mock_response

    saved_client = ts._client
    ts._client = None
    with patch.object(ts, "_get_client", AsyncMock(return_value=mock_client)):
        yield mock_client
    ts._client = saved_client


class TestSendTelegram:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_token(self):
        with patch("backend.services.telegram_service.settings") as mock:
            mock.telegram_bot_token = ""
            result = await send_telegram("sendMessage", {"chat_id": 123})
            assert result is None

    @pytest.mark.asyncio
    async def test_calls_correct_url(self, mock_settings, mock_httpx):
        await send_telegram("sendMessage", {"chat_id": 123, "text": "hi"})
        mock_httpx.post.assert_called_once()
        call_url = mock_httpx.post.call_args[0][0]
        assert "bot" + "test-token-123" in call_url
        assert "sendMessage" in call_url

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error(self, mock_settings, mock_httpx):
        mock_httpx.post.return_value.status_code = 400
        result = await send_telegram("sendMessage", {"chat_id": 123})
        assert result is None


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_sends_with_correct_params(self, mock_settings, mock_httpx):
        await send_message(123, "hello")
        payload = mock_httpx.post.call_args[1]["json"]
        assert payload["chat_id"] == 123
        assert payload["text"] == "hello"
        assert payload["parse_mode"] == "Markdown"


class TestSendMenu:
    @pytest.mark.asyncio
    async def test_sends_inline_keyboard(self, mock_settings, mock_httpx):
        await send_menu(123)
        payload = mock_httpx.post.call_args[1]["json"]
        assert "reply_markup" in payload
        assert "inline_keyboard" in payload["reply_markup"]


class TestAnswerCallback:
    @pytest.mark.asyncio
    async def test_calls_answer_callback_query(self, mock_settings, mock_httpx):
        await answer_callback("callback-123")
        call_url = mock_httpx.post.call_args[0][0]
        assert "answerCallbackQuery" in call_url


class TestHandleMenuCallback:
    @pytest.mark.asyncio
    async def test_valid_callback_sends_response(self, mock_settings, mock_httpx):
        result = await handle_menu_callback(123, "menu:gmail_scan")
        assert result is not None
        payload = mock_httpx.post.call_args[1]["json"]
        assert payload["chat_id"] == 123
        assert "Gmail" in payload["text"]

    @pytest.mark.asyncio
    async def test_invalid_callback_returns_none(self, mock_settings, mock_httpx):
        result = await handle_menu_callback(123, "menu:nonexistent")
        assert result is None


class TestRegisterBotCommands:
    @pytest.mark.asyncio
    async def test_calls_set_my_commands(self, mock_settings, mock_httpx):
        await register_bot_commands()
        call_url = mock_httpx.post.call_args[0][0]
        assert "setMyCommands" in call_url
