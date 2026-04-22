"""Tests for onboarding flow state machine, service validation, and
the webhook integration points.

Scope: pure-logic validators and the goal/keyboard wiring. DB-touching
behaviour (set_step, mark_completed, ...) is covered via integration
tests when a real Postgres is available — here we stick to mocks.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import onboarding as onb_handlers
from backend.bot.personality.onboarding_flow import (
    GOAL_RESPONSES,
    PRIMARY_GOALS,
    OnboardingStep,
)
from backend.services import onboarding_service


# ----- validate_display_name ------------------------------------------

class TestValidateDisplayName:
    def test_accepts_normal_name(self):
        ok, name = onboarding_service.validate_display_name("Minh")
        assert ok is True
        assert name == "Minh"

    def test_trims_whitespace(self):
        ok, name = onboarding_service.validate_display_name("  Trang  ")
        assert ok is True
        assert name == "Trang"

    def test_rejects_empty_string(self):
        ok, name = onboarding_service.validate_display_name("")
        assert ok is False
        assert name is None

    def test_rejects_whitespace_only(self):
        ok, name = onboarding_service.validate_display_name("   ")
        assert ok is False

    def test_rejects_too_long(self):
        ok, _ = onboarding_service.validate_display_name("x" * 51)
        assert ok is False

    def test_accepts_exactly_max(self):
        ok, _ = onboarding_service.validate_display_name("x" * 50)
        assert ok is True


class TestIsValidGoalCode:
    def test_accepts_known_codes(self):
        for code in PRIMARY_GOALS:
            assert onboarding_service.is_valid_goal_code(code) is True

    def test_rejects_unknown(self):
        assert onboarding_service.is_valid_goal_code("random") is False
        assert onboarding_service.is_valid_goal_code("") is False


# ----- Flow constants -------------------------------------------------

class TestOnboardingFlow:
    def test_steps_have_expected_values(self):
        assert OnboardingStep.NOT_STARTED == 0
        assert OnboardingStep.WELCOME == 1
        assert OnboardingStep.ASKING_NAME == 2
        assert OnboardingStep.ASKING_GOAL == 3
        assert OnboardingStep.FIRST_TRANSACTION == 4
        assert OnboardingStep.COMPLETED == 5

    def test_each_goal_has_personalised_response(self):
        for code in PRIMARY_GOALS:
            assert code in GOAL_RESPONSES
            assert len(GOAL_RESPONSES[code]) > 0

    def test_four_primary_goals(self):
        assert set(PRIMARY_GOALS) == {
            "save_more", "understand", "reach_goal", "less_stress"
        }


# ----- Keyboard generators -------------------------------------------

class TestKeyboards:
    def test_welcome_keyboard_has_two_buttons(self):
        kb = onb_handlers._welcome_keyboard()
        buttons = kb["inline_keyboard"][0]
        assert len(buttons) == 2
        assert buttons[0]["callback_data"] == "onboarding:start"
        assert buttons[1]["callback_data"] == "onboarding:skip"

    def test_goal_keyboard_has_four_buttons(self):
        kb = onb_handlers._goal_keyboard()
        rows = kb["inline_keyboard"]
        assert len(rows) == 4
        codes = [row[0]["callback_data"] for row in rows]
        assert codes == [
            "onboarding:goal:save_more",
            "onboarding:goal:understand",
            "onboarding:goal:reach_goal",
            "onboarding:goal:less_stress",
        ]

    def test_completion_keyboard_has_one_button(self):
        kb = onb_handlers._completion_keyboard()
        buttons = kb["inline_keyboard"][0]
        assert len(buttons) == 1
        assert buttons[0]["callback_data"] == "onboarding:complete"


# ----- Callback routing -----------------------------------------------

@pytest.mark.asyncio
class TestStep5AhaAdvancesState:
    """After step 5 fires, the user must no longer be in
    FIRST_TRANSACTION so a second expense does not re-trigger the
    aha moment or duplicate funnel events.
    """

    @patch(
        "backend.bot.handlers.onboarding.onboarding_service.mark_completed",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.bot.handlers.onboarding.send_message",
        new_callable=AsyncMock,
    )
    async def test_step_5_marks_user_completed(self, _send, mark_completed):
        from backend.bot.handlers.onboarding import step_5_aha_moment
        from datetime import datetime, timezone
        user = MagicMock()
        user.id = "uuid-placeholder"
        user.get_greeting_name.return_value = "Minh"
        user.created_at = datetime.now(timezone.utc)
        user.onboarding_completed_at = None

        await step_5_aha_moment(db=MagicMock(), chat_id=111, user=user)
        mark_completed.assert_awaited_once()


@pytest.mark.asyncio
class TestOnboardingCallbackRouting:
    @patch("backend.bot.handlers.onboarding.answer_callback", new_callable=AsyncMock)
    async def test_ignores_non_onboarding_callback(self, _):
        db = MagicMock()
        handled = await onb_handlers.handle_onboarding_callback(
            db, {"id": "cb", "data": "menu:report"}
        )
        assert handled is False

    @patch(
        "backend.bot.handlers.onboarding.onboarding_service.get_user_by_telegram_id",
        new_callable=AsyncMock,
    )
    @patch("backend.bot.handlers.onboarding.answer_callback", new_callable=AsyncMock)
    async def test_unknown_user_is_answered(self, mock_answer, mock_lookup):
        mock_lookup.return_value = None
        db = MagicMock()
        handled = await onb_handlers.handle_onboarding_callback(
            db,
            {
                "id": "cb",
                "data": "onboarding:start",
                "from": {"id": 42},
                "message": {
                    "chat": {"id": 99},
                    "message_id": 1,
                },
            },
        )
        assert handled is True
        mock_answer.assert_called_once()
