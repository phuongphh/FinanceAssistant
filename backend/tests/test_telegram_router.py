"""Tests for telegram router — webhook handling and authentication."""
import hmac
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


class TestWebhookAuth:
    def test_rejects_invalid_secret(self):
        with patch("backend.routers.telegram.settings") as mock:
            mock.telegram_webhook_secret = "correct-secret"
            resp = client.post(
                "/api/v1/telegram/webhook",
                json={"message": {"text": "/menu", "chat": {"id": 123}}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
            )
            assert resp.status_code == 403

    def test_accepts_valid_secret(self):
        with patch("backend.routers.telegram.settings") as mock_settings, \
             patch("backend.routers.telegram.send_menu", new_callable=AsyncMock) as mock_send:
            mock_settings.telegram_webhook_secret = "correct-secret"
            mock_send.return_value = {"ok": True}
            resp = client.post(
                "/api/v1/telegram/webhook",
                json={"message": {"text": "/menu", "chat": {"id": 123}}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
            )
            assert resp.status_code == 200

    def test_skips_validation_when_no_secret_configured(self):
        with patch("backend.routers.telegram.settings") as mock_settings, \
             patch("backend.routers.telegram.send_menu", new_callable=AsyncMock) as mock_send:
            mock_settings.telegram_webhook_secret = ""
            mock_send.return_value = {"ok": True}
            resp = client.post(
                "/api/v1/telegram/webhook",
                json={"message": {"text": "/menu", "chat": {"id": 123}}},
            )
            assert resp.status_code == 200


class TestWebhookMenuCommand:
    @patch("backend.routers.telegram.send_menu", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_menu_command(self, mock_settings, mock_send):
        mock_settings.telegram_webhook_secret = ""
        mock_send.return_value = {"ok": True}
        resp = client.post(
            "/api/v1/telegram/webhook",
            json={"message": {"text": "/menu", "chat": {"id": 123}}},
        )
        assert resp.status_code == 200
        mock_send.assert_called_once_with(123)

    @patch("backend.routers.telegram.send_menu", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_start_command(self, mock_settings, mock_send):
        mock_settings.telegram_webhook_secret = ""
        mock_send.return_value = {"ok": True}
        resp = client.post(
            "/api/v1/telegram/webhook",
            json={"message": {"text": "/start", "chat": {"id": 123}}},
        )
        assert resp.status_code == 200
        mock_send.assert_called_once_with(123)


class TestWebhookCallback:
    @patch("backend.routers.telegram.handle_menu_callback", new_callable=AsyncMock)
    @patch("backend.routers.telegram.answer_callback", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_callback_query(self, mock_settings, mock_answer, mock_handle):
        mock_settings.telegram_webhook_secret = ""
        mock_handle.return_value = {"ok": True}
        resp = client.post(
            "/api/v1/telegram/webhook",
            json={
                "callback_query": {
                    "id": "cb-123",
                    "data": "menu:report",
                    "message": {"chat": {"id": 456}},
                },
            },
        )
        assert resp.status_code == 200
        mock_answer.assert_called_once_with("cb-123")
        mock_handle.assert_called_once_with(456, "menu:report")


class TestMenuEndpoint:
    def test_get_menu_returns_features(self):
        resp = client.get("/api/v1/telegram/menu")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "text" in data["data"]
        assert "features" in data["data"]
        assert len(data["data"]["features"]) > 0
