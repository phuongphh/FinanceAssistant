"""Tests for the chat-menu-button startup hook.

The hook is the root-cause fix for "users see old dashboard after deploy" —
it re-registers Telegram's menu button URL with the current build hash on
every boot, so the WebView can't reuse a cached HTML for the previous URL.
These tests pin the contract: correct API method, payload shape, URL bump,
and graceful skip when prerequisites are missing.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from backend.bot.setup_menu_button import (
    _bumped_mini_app_url,
    _is_ngrok_free_interstitial_host,
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
        assert url == (
            "https://example.com/miniapp/wealth?b=abc1234&source=chat_menu_button"
        )

    def test_strips_trailing_slash_on_base(self):
        url = _bumped_mini_app_url("https://example.com/", "abc1234")
        assert url == (
            "https://example.com/miniapp/wealth?b=abc1234&source=chat_menu_button"
        )

    def test_carries_source_param_to_escape_poisoned_webview_cache(self):
        # The menu URL must NOT be byte-identical to a bare ``?b=<hash>`` URL:
        # a restart recomputes the SAME build hash (it only changes when
        # asset bytes change), so ``?b`` alone can't bust a WebView entry that
        # cached a blank render. The distinct ``source`` makes it a URL the
        # WebView has never seen — the documented root-cause fix.
        url = _bumped_mini_app_url("https://example.com", "abc1234")
        assert "source=chat_menu_button" in url

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
            "https://example.com/miniapp/wealth?b=abc1234&source=chat_menu_button"
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

    @pytest.mark.asyncio
    async def test_logs_error_with_actionable_context_on_api_failure(
        self, fake_settings, caplog
    ):
        # The previous contract was "quiet None" — a Telegram 4xx left
        # operators with no signal until they tapped the button and
        # saw a blank panel. The new contract: send_telegram's existing
        # "Telegram API error: ..." log is augmented here with the URL
        # and label so a grep tells the whole story.
        caplog.set_level(logging.ERROR, logger="backend.bot.setup_menu_button")
        with patch(
            "backend.bot.setup_menu_button.send_telegram",
            AsyncMock(return_value=None),
        ):
            await setup_chat_menu_button("abc1234")
        error_records = [
            r for r in caplog.records
            if r.name == "backend.bot.setup_menu_button"
            and r.levelno >= logging.ERROR
        ]
        assert error_records, "missing ERROR log on Telegram API failure"
        message = error_records[-1].getMessage()
        assert "FAILED" in message
        assert "https://example.com/miniapp/wealth?b=abc1234" in message
        assert "💰 Tài sản" in message

    @pytest.mark.asyncio
    async def test_logs_warning_with_url_on_success(
        self, fake_settings, mock_telegram, caplog
    ):
        # WARNING level (not INFO) so the success line reaches
        # backend.error.log under the default uvicorn logging config —
        # root logger only has a stderr WARNING handler. The diagnostic
        # is what tells deploy verification "yes, the menu URL really
        # is the new one".
        caplog.set_level(logging.WARNING, logger="backend.bot.setup_menu_button")
        await setup_chat_menu_button("abc1234")
        warning_records = [
            r for r in caplog.records
            if r.name == "backend.bot.setup_menu_button"
            and r.levelno == logging.WARNING
        ]
        assert warning_records, "missing WARNING log on success"
        joined = " ".join(r.getMessage() for r in warning_records)
        assert "Chat menu button synced" in joined
        assert "https://example.com/miniapp/wealth?b=abc1234" in joined

    @pytest.mark.asyncio
    async def test_warns_on_ngrok_free_dev_host(
        self, fake_settings, mock_telegram, caplog
    ):
        # ngrok-free.dev/.app trigger ngrok's abuse interstitial on any
        # Mozilla-prefixed UA — i.e. every Telegram WebView. The button
        # is still registered (devs may bypass via a manual click-through)
        # but we surface a loud WARNING with the upgrade path so the
        # blank-panel mystery doesn't repeat itself.
        fake_settings.miniapp_base_url = (
            "https://unluckily-appointee-siesta.ngrok-free.dev"
        )
        caplog.set_level(logging.WARNING, logger="backend.bot.setup_menu_button")
        await setup_chat_menu_button("abc1234")
        warning_msgs = [
            r.getMessage() for r in caplog.records
            if r.name == "backend.bot.setup_menu_button"
            and r.levelno == logging.WARNING
        ]
        assert any("ngrok-free" in m for m in warning_msgs), (
            f"expected ngrok-free warning, got: {warning_msgs}"
        )
        # Telegram is still called — registration is best-effort.
        mock_telegram.assert_called_once()

    @pytest.mark.asyncio
    async def test_warns_on_ngrok_free_app_host(
        self, fake_settings, mock_telegram, caplog
    ):
        # ngrok migrated free domains from .dev to .app over time;
        # both still serve the interstitial.
        fake_settings.miniapp_base_url = "https://abc.ngrok-free.app"
        caplog.set_level(logging.WARNING, logger="backend.bot.setup_menu_button")
        await setup_chat_menu_button("abc1234")
        warning_msgs = [
            r.getMessage() for r in caplog.records
            if r.name == "backend.bot.setup_menu_button"
            and r.levelno == logging.WARNING
        ]
        assert any("ngrok-free" in m for m in warning_msgs)

    @pytest.mark.asyncio
    async def test_does_not_warn_on_safe_tunnel_hosts(
        self, fake_settings, mock_telegram, caplog
    ):
        # Cloudflare quick-tunnels and named tunnels don't have an
        # interstitial; the warning must not fire there or it'd
        # cry-wolf operators into ignoring the real signal.
        for safe_url in (
            "https://random-words.trycloudflare.com",
            "https://bot.nuitruc.ai",
            "https://app.example.com",
        ):
            caplog.clear()
            fake_settings.miniapp_base_url = safe_url
            caplog.set_level(
                logging.WARNING,
                logger="backend.bot.setup_menu_button",
            )
            await setup_chat_menu_button("abc1234")
            warning_msgs = [
                r.getMessage() for r in caplog.records
                if r.name == "backend.bot.setup_menu_button"
                and r.levelno == logging.WARNING
            ]
            assert not any("ngrok-free" in m for m in warning_msgs), (
                f"false-positive ngrok warning for {safe_url}: {warning_msgs}"
            )


class TestNgrokFreeDetection:
    """Pin the hostname-matching contract used by the startup warning."""

    @pytest.mark.parametrize("base_url", [
        "https://abc.ngrok-free.dev",
        "https://abc.ngrok-free.dev/",
        "https://abc.ngrok-free.dev/miniapp/wealth",
        "https://abc.ngrok-free.app",
        "https://nested.subdomain.ngrok-free.dev",
        "HTTPS://CAPITALIZED.NGROK-FREE.DEV",  # case-insensitive
    ])
    def test_detects_interstitial_hosts(self, base_url):
        assert _is_ngrok_free_interstitial_host(base_url) is True

    @pytest.mark.parametrize("base_url", [
        # Safe tunnels / production hosts:
        "https://app.example.com",
        "https://random.trycloudflare.com",
        "https://bot.nuitruc.ai",
        # Substring traps — must NOT match in the middle of a host:
        "https://ngrok-free.dev.evil.com",
        "https://my-ngrok-free.dev-clone.com",
        # Empty / invalid:
        "",
        "not-a-url",
    ])
    def test_does_not_flag_safe_hosts(self, base_url):
        assert _is_ngrok_free_interstitial_host(base_url) is False
