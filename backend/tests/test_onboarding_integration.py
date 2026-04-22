"""End-to-end integration tests for the onboarding flow.

Drives the Telegram webhook with realistic payloads across every
step of the 5-step state machine and asserts that the correct
handler fires. DB interactions are stubbed at the service boundary
so these tests run in CI without Postgres.

This complements the unit tests in:
- test_onboarding.py (pure logic + callback router)
- test_onboarding_service.py (DB setters)
- test_telegram_router.py (command routing shape)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.bot.personality.onboarding_flow import OnboardingStep
from backend.main import app

client = TestClient(app)


def _fake_user(step: int = 0, is_onboarded: bool = False):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.telegram_id = 999
    user.display_name = None
    user.primary_goal = None
    user.onboarding_step = step
    user.onboarding_completed_at = None
    user.onboarding_skipped = False
    user.is_onboarded = is_onboarded
    user.get_greeting_name.return_value = (
        user.display_name if user.display_name else "bạn"
    )
    return user


class TestOnboardingWebhookFlow:
    """Drive the webhook through each step of the 5-step onboarding."""

    @patch("backend.routers.telegram.onboarding_handlers.send_welcome_back", new_callable=AsyncMock)
    @patch("backend.routers.telegram.onboarding_handlers.step_1_welcome", new_callable=AsyncMock)
    @patch(
        "backend.routers.telegram.dashboard_service.get_or_create_user",
        new_callable=AsyncMock,
    )
    @patch("backend.routers.telegram.settings")
    def test_start_for_new_user_triggers_welcome(
        self, mock_settings, mock_get_or_create, mock_step_1, mock_welcome_back
    ):
        mock_settings.telegram_webhook_secret = ""
        user = _fake_user(step=0, is_onboarded=False)
        mock_get_or_create.return_value = (user, True)

        resp = client.post(
            "/api/v1/telegram/webhook",
            json={
                "message": {
                    "text": "/start",
                    "chat": {"id": 123},
                    "from": {"id": 999, "username": "minh"},
                }
            },
        )

        assert resp.status_code == 200
        mock_step_1.assert_awaited_once()
        mock_welcome_back.assert_not_called()

    @patch("backend.routers.telegram.onboarding_handlers.send_welcome_back", new_callable=AsyncMock)
    @patch("backend.routers.telegram.onboarding_handlers.step_1_welcome", new_callable=AsyncMock)
    @patch(
        "backend.routers.telegram.dashboard_service.get_or_create_user",
        new_callable=AsyncMock,
    )
    @patch("backend.routers.telegram.settings")
    def test_start_for_already_onboarded_user_skips_onboarding(
        self, mock_settings, mock_get_or_create, mock_step_1, mock_welcome_back
    ):
        mock_settings.telegram_webhook_secret = ""
        user = _fake_user(step=5, is_onboarded=True)
        mock_get_or_create.return_value = (user, False)

        resp = client.post(
            "/api/v1/telegram/webhook",
            json={
                "message": {
                    "text": "/start",
                    "chat": {"id": 123},
                    "from": {"id": 999},
                }
            },
        )

        assert resp.status_code == 200
        mock_welcome_back.assert_awaited_once()
        mock_step_1.assert_not_called()

    @patch("backend.routers.telegram.onboarding_handlers.handle_name_input", new_callable=AsyncMock)
    @patch(
        "backend.routers.telegram.dashboard_service.get_user_by_telegram_id",
        new_callable=AsyncMock,
    )
    @patch("backend.routers.telegram.handle_text_message", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_free_text_during_asking_name_routes_to_name_handler(
        self,
        mock_settings,
        mock_text_message,
        mock_lookup,
        mock_name_input,
    ):
        mock_settings.telegram_webhook_secret = ""
        mock_lookup.return_value = _fake_user(
            step=int(OnboardingStep.ASKING_NAME)
        )
        mock_name_input.return_value = True  # text was consumed

        resp = client.post(
            "/api/v1/telegram/webhook",
            json={
                "message": {
                    "text": "Minh",
                    "chat": {"id": 123},
                    "from": {"id": 999},
                }
            },
        )

        assert resp.status_code == 200
        mock_name_input.assert_awaited_once()
        # NL expense handler must NOT run for onboarding name input.
        mock_text_message.assert_not_called()

    @patch("backend.routers.telegram.onboarding_handlers.handle_name_input", new_callable=AsyncMock)
    @patch(
        "backend.routers.telegram.dashboard_service.get_user_by_telegram_id",
        new_callable=AsyncMock,
    )
    @patch("backend.routers.telegram.handle_text_message", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_free_text_outside_onboarding_routes_to_nl_handler(
        self,
        mock_settings,
        mock_text_message,
        mock_lookup,
        mock_name_input,
    ):
        mock_settings.telegram_webhook_secret = ""
        # User is past onboarding — plain text should be treated as a
        # natural-language expense.
        mock_lookup.return_value = _fake_user(
            step=int(OnboardingStep.COMPLETED), is_onboarded=True
        )

        resp = client.post(
            "/api/v1/telegram/webhook",
            json={
                "message": {
                    "text": "45k phở",
                    "chat": {"id": 123},
                    "from": {"id": 999},
                }
            },
        )

        assert resp.status_code == 200
        mock_name_input.assert_not_called()
        mock_text_message.assert_awaited_once()

    @patch("backend.routers.telegram.onboarding_handlers.handle_onboarding_callback", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_goal_callback_routed_to_onboarding_handler(
        self, mock_settings, mock_onboarding_cb
    ):
        mock_settings.telegram_webhook_secret = ""
        mock_onboarding_cb.return_value = True  # handled

        resp = client.post(
            "/api/v1/telegram/webhook",
            json={
                "callback_query": {
                    "id": "cb-1",
                    "data": "onboarding:goal:save_more",
                    "from": {"id": 999},
                    "message": {
                        "chat": {"id": 123},
                        "message_id": 42,
                    },
                }
            },
        )

        assert resp.status_code == 200
        mock_onboarding_cb.assert_awaited_once()
