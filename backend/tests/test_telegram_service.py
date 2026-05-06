"""Tests for telegram_service — Telegram API transport layer."""
from unittest.mock import AsyncMock, patch

import pytest

from backend.bot.setup_commands import setup_bot_commands
from backend.services.telegram_service import (
    answer_callback,
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

    @pytest.mark.asyncio
    async def test_retries_without_parse_mode_on_parse_entities_error(
        self, mock_settings, mock_httpx
    ):
        """Last-resort retry: even if the sanitizer (#231) misses a case
        and Telegram still rejects, we drop ``parse_mode`` so the user
        sees raw text instead of nothing.

        Uses input the sanitizer leaves alone (already-balanced) so the
        body Telegram rejects is identical to the body we sent. This
        keeps the test focused on the retry behaviour, not the sanitizer
        (which has its own dedicated tests).
        """
        from unittest.mock import MagicMock

        bad_response = MagicMock()
        bad_response.status_code = 400
        bad_response.text = (
            '{"ok":false,"error_code":400,'
            '"description":"Bad Request: can\'t parse entities: '
            'Can\'t find end of the entity starting at byte offset 1217"}'
        )
        good_response = MagicMock()
        good_response.status_code = 200
        good_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
        good_response.text = '{"ok": true}'
        mock_httpx.post.side_effect = [bad_response, good_response]

        result = await send_telegram(
            "sendMessage",
            {
                "chat_id": 123,
                "text": "hi *balanced* text",
                "parse_mode": "Markdown",
            },
        )

        assert result == {"ok": True, "result": {"message_id": 1}}
        assert mock_httpx.post.call_count == 2
        # Retry payload must NOT carry parse_mode anymore.
        retry_payload = mock_httpx.post.call_args_list[1][1]["json"]
        assert "parse_mode" not in retry_payload
        assert retry_payload["text"] == "hi *balanced* text"
        assert retry_payload["chat_id"] == 123

    @pytest.mark.asyncio
    async def test_no_retry_when_400_is_not_parse_entities(
        self, mock_settings, mock_httpx
    ):
        """Other 400s (chat not found, etc.) must not trigger a retry."""
        from unittest.mock import MagicMock

        bad_response = MagicMock()
        bad_response.status_code = 400
        bad_response.text = (
            '{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'
        )
        mock_httpx.post.side_effect = None
        mock_httpx.post.return_value = bad_response

        result = await send_telegram(
            "sendMessage",
            {"chat_id": 123, "text": "hi", "parse_mode": "Markdown"},
        )

        assert result is None
        assert mock_httpx.post.call_count == 1


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_sends_with_correct_params(self, mock_settings, mock_httpx):
        await send_message(123, "hello")
        payload = mock_httpx.post.call_args[1]["json"]
        assert payload["chat_id"] == 123
        assert payload["text"] == "hello"
        assert payload["parse_mode"] == "Markdown"


class TestPreSendSanitization:
    """The sanitizer must run BEFORE the HTTP call so unbalanced markdown
    never reaches Telegram in the first place. The plain-text retry
    (#230) stays as a fallback, but should rarely fire after this.
    """

    @pytest.mark.asyncio
    async def test_unbalanced_bold_is_escaped_before_send(
        self, mock_settings, mock_httpx
    ):
        await send_telegram(
            "sendMessage",
            {
                "chat_id": 123,
                "text": "Mua *VinHomes",  # truncated mid-bold
                "parse_mode": "Markdown",
            },
        )
        sent_payload = mock_httpx.post.call_args[1]["json"]
        # Sanitizer escaped the stray ``*`` so Telegram parses cleanly.
        assert sent_payload["text"] == "Mua \\*VinHomes"
        # Single API call — no retry needed because the body is now valid.
        assert mock_httpx.post.call_count == 1

    @pytest.mark.asyncio
    async def test_list_bullets_are_escaped_before_send(
        self, mock_settings, mock_httpx
    ):
        await send_telegram(
            "sendMessage",
            {
                "chat_id": 123,
                "text": "Gợi ý:\n* Mục 1\n* Mục 2",
                "parse_mode": "Markdown",
            },
        )
        sent_payload = mock_httpx.post.call_args[1]["json"]
        assert "\\* Mục 1" in sent_payload["text"]
        assert "\\* Mục 2" in sent_payload["text"]

    @pytest.mark.asyncio
    async def test_balanced_markdown_passes_through_unchanged(
        self, mock_settings, mock_httpx
    ):
        original = "Hôm nay *quan trọng* và _gợi ý_ cho bạn."
        await send_telegram(
            "sendMessage",
            {"chat_id": 123, "text": original, "parse_mode": "Markdown"},
        )
        sent_payload = mock_httpx.post.call_args[1]["json"]
        assert sent_payload["text"] == original

    @pytest.mark.asyncio
    async def test_html_mode_is_not_touched_by_sanitizer(
        self, mock_settings, mock_httpx
    ):
        # The sanitizer only knows Markdown; HTML has its own escaping.
        original = "<b>Hello *world*</b>"
        await send_telegram(
            "sendMessage",
            {"chat_id": 123, "text": original, "parse_mode": "HTML"},
        )
        sent_payload = mock_httpx.post.call_args[1]["json"]
        assert sent_payload["text"] == original

    @pytest.mark.asyncio
    async def test_no_parse_mode_skips_sanitizer(
        self, mock_settings, mock_httpx
    ):
        # Plain text doesn't need sanitization.
        original = "Mua *VinHomes (raw text, no parser)"
        await send_telegram(
            "sendMessage", {"chat_id": 123, "text": original}
        )
        sent_payload = mock_httpx.post.call_args[1]["json"]
        assert sent_payload["text"] == original

    @pytest.mark.asyncio
    async def test_edit_message_text_also_sanitized(
        self, mock_settings, mock_httpx
    ):
        await send_telegram(
            "editMessageText",
            {
                "chat_id": 123,
                "message_id": 456,
                "text": "Cập nhật *truncated",
                "parse_mode": "Markdown",
            },
        )
        sent_payload = mock_httpx.post.call_args[1]["json"]
        assert sent_payload["text"] == "Cập nhật \\*truncated"

    @pytest.mark.asyncio
    async def test_non_text_method_payload_untouched(
        self, mock_settings, mock_httpx
    ):
        # answerCallbackQuery has no body; sanitizer must be a no-op.
        await send_telegram(
            "answerCallbackQuery",
            {"callback_query_id": "cb-1", "text": "Stray *marker"},
        )
        sent_payload = mock_httpx.post.call_args[1]["json"]
        # No parse_mode means the sanitizer's gate skips this anyway,
        # and we don't have answerCallbackQuery in the field map.
        assert sent_payload["text"] == "Stray *marker"


class TestAnswerCallback:
    @pytest.mark.asyncio
    async def test_calls_answer_callback_query(self, mock_settings, mock_httpx):
        await answer_callback("callback-123")
        call_url = mock_httpx.post.call_args[0][0]
        assert "answerCallbackQuery" in call_url


class TestSetupBotCommands:
    @pytest.mark.asyncio
    async def test_calls_set_my_commands(self, mock_settings, mock_httpx):
        await setup_bot_commands()
        call_url = mock_httpx.post.call_args[0][0]
        assert "setMyCommands" in call_url

    @pytest.mark.asyncio
    async def test_sends_4_phase_36_commands(self, mock_settings, mock_httpx):
        await setup_bot_commands()
        payload = mock_httpx.post.call_args[1]["json"]
        commands = payload["commands"]
        names = [c["command"] for c in commands]
        assert names == ["start", "menu", "help", "dashboard"]
        # No deprecated V1 commands surfaced — Phase 3.6 cuts the list.
        for legacy in ("themtaisan", "taisan", "report", "goals", "market"):
            assert legacy not in names
