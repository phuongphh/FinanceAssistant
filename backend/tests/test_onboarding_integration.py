"""Integration tests for the onboarding dispatch flow.

After the Phase A refactor (docs/archive/scaling-refactor-A.md) the
webhook route only verifies + claims + enqueues. All dispatch logic
lives in ``backend.workers.telegram_worker.route_update``. These tests
drive ``route_update`` directly with realistic Telegram payloads — that
is both simpler (no HTTP layer) and correct (handler mocks are observed
synchronously, unlike a background ``asyncio.create_task``).

DB interactions are stubbed at the service boundary so these tests run
in CI without Postgres.

Complements the unit tests in:
- test_onboarding.py (pure logic + callback router)
- test_onboarding_service.py (DB setters)
- test_telegram_router.py (auth + enqueue contract)
- test_telegram_worker.py (worker internals + recovery)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.personality.onboarding_flow import OnboardingStep
from backend.workers import telegram_worker


def _fake_user(
    step: int = 0,
    is_onboarded: bool = False,
    wizard_state: dict | None = None,
):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.telegram_id = 999
    user.display_name = None
    user.primary_goal = None
    user.onboarding_step = step
    user.onboarding_completed_at = None
    user.onboarding_skipped = False
    user.is_onboarded = is_onboarded
    # Phase 3A added ``wizard_state`` (storytelling / asset-entry); the
    # worker's text dispatch peeks at it BEFORE falling through to the
    # NL parser. MagicMock auto-mocks any attribute as truthy, so
    # without an explicit ``None`` here every text path gets routed
    # through the asset-wizard branch and ``handle_text_message`` is
    # never reached. Default to ``None`` so tests opt in explicitly
    # when they want to exercise the wizard branches.
    user.wizard_state = wizard_state
    user.get_greeting_name.return_value = (
        user.display_name if user.display_name else "bạn"
    )
    return user


def _fake_session():
    """Minimal async-session double for route_update to commit against."""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    # Post Phase B1: services flush; await-able to avoid MagicMock
    # auto-creating a non-coroutine attribute if a handler calls into
    # a real service under these mocks.
    session.flush = AsyncMock()
    # route_update issues UPDATE telegram_updates SET user_id = ?
    # before committing — execute must be awaitable.
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    return session


class TestOnboardingDispatch:
    """Drive route_update through each step of the 5-step onboarding."""

    @pytest.mark.asyncio
    @patch("backend.bot.handlers.onboarding.send_welcome_back", new_callable=AsyncMock)
    @patch("backend.bot.handlers.onboarding.step_1_welcome", new_callable=AsyncMock)
    @patch("backend.services.dashboard_service.get_or_create_user", new_callable=AsyncMock)
    async def test_start_for_new_user_triggers_welcome(
        self, mock_get_or_create, mock_step_1, mock_welcome_back
    ):
        user = _fake_user(step=0, is_onboarded=False)
        mock_get_or_create.return_value = (user, True)

        sess = _fake_session()
        with patch.object(
            telegram_worker, "get_session_factory",
            return_value=MagicMock(return_value=sess),
        ):
            await telegram_worker.route_update({
                "update_id": 1,
                "message": {
                    "text": "/start",
                    "chat": {"id": 123},
                    "from": {"id": 999, "username": "minh"},
                },
            })

        mock_step_1.assert_awaited_once()
        mock_welcome_back.assert_not_called()

    @pytest.mark.asyncio
    @patch("backend.bot.handlers.onboarding.send_welcome_back", new_callable=AsyncMock)
    @patch("backend.bot.handlers.onboarding.step_1_welcome", new_callable=AsyncMock)
    @patch("backend.services.dashboard_service.get_or_create_user", new_callable=AsyncMock)
    async def test_start_for_already_onboarded_user_skips_onboarding(
        self, mock_get_or_create, mock_step_1, mock_welcome_back
    ):
        user = _fake_user(step=5, is_onboarded=True)
        mock_get_or_create.return_value = (user, False)

        sess = _fake_session()
        with patch.object(
            telegram_worker, "get_session_factory",
            return_value=MagicMock(return_value=sess),
        ):
            await telegram_worker.route_update({
                "update_id": 2,
                "message": {
                    "text": "/start",
                    "chat": {"id": 123},
                    "from": {"id": 999},
                },
            })

        mock_welcome_back.assert_awaited_once()
        mock_step_1.assert_not_called()

    @pytest.mark.asyncio
    @patch("backend.bot.handlers.onboarding.handle_name_input", new_callable=AsyncMock)
    @patch("backend.services.dashboard_service.get_user_by_telegram_id", new_callable=AsyncMock)
    @patch("backend.bot.handlers.message.handle_text_message", new_callable=AsyncMock)
    async def test_free_text_during_asking_name_routes_to_name_handler(
        self, mock_text_message, mock_lookup, mock_name_input
    ):
        mock_lookup.return_value = _fake_user(step=int(OnboardingStep.ASKING_NAME))
        mock_name_input.return_value = True  # consumed

        sess = _fake_session()
        with patch.object(
            telegram_worker, "get_session_factory",
            return_value=MagicMock(return_value=sess),
        ):
            await telegram_worker.route_update({
                "update_id": 3,
                "message": {
                    "text": "Minh",
                    "chat": {"id": 123},
                    "from": {"id": 999},
                },
            })

        mock_name_input.assert_awaited_once()
        # NL expense handler must NOT run for onboarding name input.
        mock_text_message.assert_not_called()

    @pytest.mark.asyncio
    @patch("backend.bot.handlers.onboarding.handle_name_input", new_callable=AsyncMock)
    @patch("backend.services.dashboard_service.get_user_by_telegram_id", new_callable=AsyncMock)
    @patch("backend.bot.handlers.message.handle_text_message", new_callable=AsyncMock)
    async def test_free_text_outside_onboarding_routes_to_nl_handler(
        self, mock_text_message, mock_lookup, mock_name_input
    ):
        mock_lookup.return_value = _fake_user(
            step=int(OnboardingStep.COMPLETED), is_onboarded=True
        )

        sess = _fake_session()
        with patch.object(
            telegram_worker, "get_session_factory",
            return_value=MagicMock(return_value=sess),
        ):
            await telegram_worker.route_update({
                "update_id": 4,
                "message": {
                    "text": "45k phở",
                    "chat": {"id": 123},
                    "from": {"id": 999},
                },
            })

        mock_name_input.assert_not_called()
        mock_text_message.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(
        "backend.services.dashboard_service.get_user_by_telegram_id",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.bot.handlers.onboarding.handle_onboarding_callback",
        new_callable=AsyncMock,
    )
    async def test_goal_callback_routed_to_onboarding_handler(
        self, mock_onboarding_cb, mock_lookup
    ):
        mock_onboarding_cb.return_value = True  # handled
        mock_lookup.return_value = _fake_user(
            step=int(OnboardingStep.COMPLETED), is_onboarded=True
        )

        sess = _fake_session()
        with patch.object(
            telegram_worker, "get_session_factory",
            return_value=MagicMock(return_value=sess),
        ):
            await telegram_worker.route_update({
                "update_id": 5,
                "callback_query": {
                    "id": "cb-1",
                    "data": "onboarding:goal:save_more",
                    "from": {"id": 999},
                    "message": {"chat": {"id": 123}, "message_id": 42},
                },
            })

        mock_onboarding_cb.assert_awaited_once()
