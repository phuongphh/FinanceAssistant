"""Tests for the chat-menu-button startup hook.

The hook is the root-cause fix for "users see old dashboard after deploy" —
it re-registers Telegram's menu button URL with the current build hash on
every boot, so the WebView can't reuse a cached HTML for the previous URL.
These tests pin the contract: correct API method, payload shape, URL bump,
and graceful skip when prerequisites are missing.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.bot.setup_menu_button import (
    _bumped_mini_app_url,
    setup_chat_menu_button,
)


@pytest.fixture
def mock_telegram(monkeypatch):
    """Patch ``send_telegram`` so tests inspect the payload instead of
    hitting the real API. Returning ``{"ok": True}`` keeps the success
    branch live (logger.info gets exercised)."""
    fake = AsyncMock(return_value={"ok": True, "result": True})
    monkeypatch.setattr(
        "backend.bot.setup_menu_button.send_telegram", fake
    )
    return fake


@pytest.fixture
def fake_settings(monkeypatch):
    """In-memory Settings stand-in. Each test mutates fields directly to
    cover a specific branch without touching the real .env file."""

    class _S:
        telegram_bot_token = "test-token"
        miniapp_base_url = "https://example.com"
        miniapp_menu_label = "💰 Tài sản"

    s = _S()
    monkeypatch.setattr(
        "backend.bot.setup_menu_button.get_settings", lambda: s
    )
    return s


class TestBumpedMiniAppUrl:
    def test_appends_build_hash_query_param(self):
        url = _bumped_mini_app_url("https://example.com", "abc1234")
        assert url == "https://example.com/miniapp/wealth?b=abc1234"

    def test_strips_trailing_slash_on_base(self):
        url = _bumped_mini_app_url("https://example.com/", "abc1234")
        assert url == "https://example.com/miniapp/wealth?b=abc1234"

    def test_replaces_stale_b_param_on_redeploy(self):
        # Defensive: even if MINIAPP_BASE_URL were ever set with a leftover
        # ``?b=`` from a previous bump, we overwrite — never accumulate.
        url = _bumped_mini_app_url(
            "https://example.com/miniapp/wealth?b=oldhash", "newhash"
        )
        assert "b=newhash" in url
        assert "oldhash" not in url


class TestSetupChatMenuButton:
    @pytest.mark.asyncio
    async def test_calls_set_chat_menu_button_method(
        self, fake_settings, mock_telegram
    ):
        await setup_chat_menu_button("abc1234")
        method = mock_telegram.call_args[0][0]
        assert method == "setChatMenuButton"

    @pytest.mark.asyncio
    async def test_payload_uses_web_app_type_with_label_and_bumped_url(
        self, fake_settings, mock_telegram
    ):
        await setup_chat_menu_button("abc1234")
        payload = mock_telegram.call_args[0][1]
        button = payload["menu_button"]
        assert button["type"] == "web_app"
        assert button["text"] == "💰 Tài sản"
        # Pin the cache-bust contract: the build hash MUST be on the URL,
        # not the document — that's the whole point of this module.
        assert button["web_app"]["url"] == (
            "https://example.com/miniapp/wealth?b=abc1234"
        )

    @pytest.mark.asyncio
    async def test_respects_overridden_label(
        self, fake_settings, mock_telegram
    ):
        fake_settings.miniapp_menu_label = "📊 Bảng điều khiển"
        await setup_chat_menu_button("abc1234")
        payload = mock_telegram.call_args[0][1]
        assert payload["menu_button"]["text"] == "📊 Bảng điều khiển"

    @pytest.mark.asyncio
    async def test_skips_silently_when_token_missing(
        self, fake_settings, mock_telegram
    ):
        # Dev/CI without a bot token: must NOT call the API and must NOT
        # raise — boot has to succeed without Telegram credentials.
        fake_settings.telegram_bot_token = ""
        result = await setup_chat_menu_button("abc1234")
        assert result is None
        mock_telegram.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_silently_when_base_url_missing(
        self, fake_settings, mock_telegram
    ):
        # Telegram rejects http:// on web_app, so dev tunnels without a
        # public HTTPS URL fall through cleanly — BotFather's manual
        # config still applies until the URL is set.
        fake_settings.miniapp_base_url = ""
        result = await setup_chat_menu_button("abc1234")
        assert result is None
        mock_telegram.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_telegram_api_failure(
        self, fake_settings
    ):
        # send_telegram returns None on Telegram 5xx; the hook must not
        # crash startup — the lifespan also wraps in try/except, but a
        # quiet None is the cleaner contract.
        with patch(
            "backend.bot.setup_menu_button.send_telegram",
            AsyncMock(return_value=None),
        ):
            result = await setup_chat_menu_button("abc1234")
            assert result is None
