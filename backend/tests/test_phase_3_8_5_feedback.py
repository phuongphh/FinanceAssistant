from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.feedback.handlers import feedback_command
from backend.feedback.models.feedback import Feedback, PromptSentLog
from backend.feedback.services import feedback_service
from backend.feedback.services.classifier import FeedbackClassifier, classify_feedback_batch
from backend.feedback.services.prompt_scheduler import FeedbackPrompt, PromptScheduler
from backend.models.user import User


def _user(state: dict | None = None) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 123
    u.display_name = "Test"
    u.wealth_level = "starter"
    u.wizard_state = state
    u.created_at = datetime.now(timezone.utc) - timedelta(days=7)
    u.is_active = True
    u.briefing_enabled = True
    return u


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


@pytest.mark.asyncio
async def test_feedback_creation_has_context_and_trigger():
    user = _user()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(0), MagicMock(all=lambda: [])])
    db.add = MagicMock()
    db.flush = AsyncMock()

    with patch.object(feedback_service.analytics, "track"):
        feedback = await feedback_service.create_feedback(
            db,
            user,
            "App rất tốt nhưng thiếu dark mode",
        )

    assert feedback.content == "App rất tốt nhưng thiếu dark mode"
    assert feedback.trigger == "passive_command"
    assert feedback.context["wealth_level"] == "starter"
    assert feedback.context["app_version"] == "phase-3.8.5"
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_feedback_rate_limit_blocks_sixth_submission():
    user = _user()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(5))

    with pytest.raises(feedback_service.FeedbackRateLimitError):
        await feedback_service.validate_feedback_text(db, user.id, "Feedback hợp lệ")


@pytest.mark.asyncio
async def test_feedback_command_starts_feedback_flow():
    user = _user()
    db = MagicMock()

    with patch.object(
        feedback_command.wizard_service, "start_flow", AsyncMock()
    ) as start_flow, patch.object(
        feedback_command, "send_message", AsyncMock()
    ) as send:
        await feedback_command.start_feedback(db, chat_id=123, user=user)

    start_flow.assert_awaited_once_with(
        db,
        user.id,
        flow=feedback_command.FLOW_FEEDBACK,
        step=feedback_command.STEP_AWAITING_TEXT,
        draft={"trigger": "passive_command"},
    )
    assert "lắng nghe" in send.await_args.args[1]


@pytest.mark.asyncio
async def test_feedback_cta_callback_starts_feedback_flow():
    user = _user()
    db = MagicMock()

    with patch(
        "backend.services.dashboard_service.get_user_by_telegram_id",
        AsyncMock(return_value=user),
    ), patch.object(
        feedback_command.wizard_service, "start_flow", AsyncMock()
    ) as start_flow, patch.object(
        feedback_command, "send_message", AsyncMock()
    ) as send, patch.object(
        feedback_command, "answer_callback", AsyncMock()
    ):
        handled = await feedback_command.handle_feedback_callback(
            db,
            {
                "id": "cb-cta",
                "data": "feedback:cta:post_onboarding_day_7",
                "from": {"id": 123},
                "message": {"chat": {"id": 123}},
            },
        )

    assert handled is True
    start_flow.assert_awaited_once_with(
        db,
        user.id,
        flow=feedback_command.FLOW_FEEDBACK,
        step=feedback_command.STEP_AWAITING_TEXT,
        draft={"trigger": "post_onboarding_day_7"},
    )
    assert "cảm nhận" in send.await_args.args[1]


@pytest.mark.asyncio
async def test_feedback_handler_cancel_clears_state():
    user = _user({"flow": feedback_command.FLOW_FEEDBACK, "step": "awaiting_feedback_text", "draft": {}})
    db = MagicMock()

    with patch("backend.services.dashboard_service.get_user_by_telegram_id", AsyncMock(return_value=user)), \
         patch.object(feedback_command.wizard_service, "clear", AsyncMock()) as clear, \
         patch.object(feedback_command, "send_message", AsyncMock()) as send:
        consumed = await feedback_command.handle_feedback_text_input(
            db,
            {"text": "/cancel", "chat": {"id": 123}, "from": {"id": 123}},
        )

    assert consumed is True
    clear.assert_awaited_once_with(db, user.id)
    assert "huỷ" in send.await_args.args[1]


@pytest.mark.asyncio
async def test_classifier_parses_deepseek_json():
    with patch("backend.feedback.services.classifier.call_llm", AsyncMock(return_value='{"category":"bug","sentiment":"negative","priority":"high","confidence":0.91}')):
        result = await FeedbackClassifier().classify("Bot không trả lời khi tôi gửi /menu")

    assert result["category"] == "bug"
    assert result["sentiment"] == "negative"
    assert result["priority"] == "high"
    assert result["confidence"] == 0.91


@pytest.mark.asyncio
async def test_classifier_fallback_on_invalid_json():
    with patch("backend.feedback.services.classifier.call_llm", AsyncMock(return_value="not json")):
        result = await FeedbackClassifier().classify("test")

    assert result["category"] == "other"
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_classify_feedback_batch_updates_unclassified_rows():
    feedback = Feedback(user_id=uuid.uuid4(), content="Tuyệt vời", trigger="passive_command")
    db = MagicMock()
    db.flush = AsyncMock()

    with patch("backend.feedback.services.classifier.list_unclassified_feedbacks", AsyncMock(return_value=[feedback])):
        classifier = MagicMock()
        classifier.classify = AsyncMock(return_value={
            "category": "praise",
            "sentiment": "positive",
            "priority": "low",
            "confidence": 0.8,
            "classifier_version": "test",
        })
        processed = await classify_feedback_batch(db, classifier=classifier)

    assert processed == 1
    assert feedback.category == "praise"
    assert feedback.classification_attempts == 1


@pytest.mark.asyncio
async def test_prompt_scheduler_cooldown_prevents_resend():
    user = _user()
    prompt = FeedbackPrompt(
        id="post_onboarding_day_7",
        trigger="account_age_days == 7",
        message="Hi",
        cta_button="CTA",
        skip_button="Skip",
        cooldown_days=60,
    )
    scheduler = PromptScheduler([prompt])
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.execute = AsyncMock(side_effect=[_scalar_result(0), _scalar_result(0), _scalar_result(0), _scalar_result(1)])

    sent = await scheduler.check_and_send_prompts(db, user.id, event="daily")

    assert sent == []


@pytest.mark.asyncio
async def test_prompt_scheduler_max_two_per_month_blocks_third():
    user = _user()
    prompt = FeedbackPrompt(
        id="post_onboarding_day_7",
        trigger="account_age_days == 7",
        message="Hi",
        cta_button="CTA",
        skip_button="Skip",
        cooldown_days=60,
    )
    scheduler = PromptScheduler([prompt])
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.execute = AsyncMock(side_effect=[_scalar_result(0), _scalar_result(0), _scalar_result(0), _scalar_result(0), _scalar_result(2)])

    sent = await scheduler.check_and_send_prompts(db, user.id, event="daily")

    assert sent == []


@pytest.mark.asyncio
async def test_prompt_callback_skip_logs_skip():
    user = _user()
    db = MagicMock()
    db.flush = AsyncMock()
    log = PromptSentLog(user_id=user.id, prompt_id="post_onboarding_day_7", trigger="post_onboarding_day_7")

    with patch("backend.services.dashboard_service.get_user_by_telegram_id", AsyncMock(return_value=user)), \
         patch.object(PromptScheduler, "_latest_prompt_log", AsyncMock(return_value=log)), \
         patch.object(feedback_command, "answer_callback", AsyncMock()):
        handled = await feedback_command.handle_feedback_callback(db, {
            "id": "cb1",
            "data": "feedback:skip:post_onboarding_day_7",
            "from": {"id": 123},
        })

    assert handled is True
    assert log.status == "skipped"
