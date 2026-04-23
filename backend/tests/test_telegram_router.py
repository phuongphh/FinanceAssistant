"""Tests for the telegram router — auth + webhook contract shape.

Dispatch behaviour (command routing, callback routing, onboarding) is
now tested by driving ``backend.workers.telegram_worker.route_update``
directly — see test_telegram_worker.py and test_onboarding_integration.py.
This file only covers what the HTTP layer itself owns: secret header
verification and the claim-then-enqueue contract.
"""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _noop_enqueue(update_id, data):
    """Stand-in for ``_enqueue_update`` in tests — does nothing."""


class TestWebhookAuth:
    def test_rejects_invalid_secret(self):
        with patch("backend.routers.telegram.settings") as mock:
            mock.telegram_webhook_secret = "correct-secret"
            resp = client.post(
                "/api/v1/telegram/webhook",
                json={"update_id": 1, "message": {"text": "/menu", "chat": {"id": 123}}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
            )
            assert resp.status_code == 403

    @patch("backend.routers.telegram._enqueue_update", side_effect=_noop_enqueue)
    @patch("backend.routers.telegram._claim_update", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_accepts_valid_secret(self, mock_settings, mock_claim, _mock_task):
        mock_settings.telegram_webhook_secret = "correct-secret"
        mock_claim.return_value = True
        resp = client.post(
            "/api/v1/telegram/webhook",
            json={"update_id": 2, "message": {"text": "/menu", "chat": {"id": 123}}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
        )
        assert resp.status_code == 200

    @patch("backend.routers.telegram._enqueue_update", side_effect=_noop_enqueue)
    @patch("backend.routers.telegram._claim_update", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_skips_validation_when_no_secret_configured(
        self, mock_settings, mock_claim, _mock_task
    ):
        mock_settings.telegram_webhook_secret = ""
        mock_claim.return_value = True
        resp = client.post(
            "/api/v1/telegram/webhook",
            json={"update_id": 3, "message": {"text": "/menu", "chat": {"id": 123}}},
        )
        assert resp.status_code == 200


class TestMenuEndpoint:
    def test_get_menu_returns_features(self):
        resp = client.get("/api/v1/telegram/menu")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "text" in data["data"]
        assert "features" in data["data"]
        assert len(data["data"]["features"]) > 0
