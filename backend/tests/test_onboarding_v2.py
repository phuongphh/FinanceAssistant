from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import onboarding_v2
from backend.models.onboarding_session import STEP_FIRST_ASSET, STEP_GOAL_QUESTION


def _user(display_name=None):
    user = MagicMock()
    user.id = "user-1"
    user.display_name = display_name
    return user


def _session(step=STEP_GOAL_QUESTION, goal_choice=None):
    s = MagicMock()
    s.current_step = step
    s.goal_choice = goal_choice
    return s


@pytest.mark.asyncio
async def test_handle_name_text_input_ignores_when_not_at_name_gate():
    db = MagicMock()
    user = _user()

    with patch(
        "backend.bot.handlers.onboarding_v2.onboarding_service.get_session",
        new=AsyncMock(return_value=_session(step=STEP_FIRST_ASSET)),
    ):
        consumed = await onboarding_v2.handle_name_text_input(db, 123, user, "Minh")

    assert consumed is False


@pytest.mark.asyncio
async def test_handle_name_text_input_rejects_invalid_name():
    db = MagicMock()
    user = _user()

    with patch(
        "backend.bot.handlers.onboarding_v2.onboarding_service.get_session",
        new=AsyncMock(return_value=_session()),
    ), patch(
        "backend.bot.handlers.onboarding_v2.legacy_onboarding_service.validate_display_name",
        return_value=(False, None),
    ), patch(
        "backend.bot.handlers.onboarding_v2.send_message",
        new=AsyncMock(),
    ) as send_message_mock:
        consumed = await onboarding_v2.handle_name_text_input(db, 123, user, "")

    assert consumed is True
    send_message_mock.assert_awaited_once()
    assert "Tên chưa hợp lệ" in send_message_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_handle_name_text_input_saves_name_and_moves_to_goal():
    db = MagicMock()
    db.flush = AsyncMock()
    user = _user()

    with patch(
        "backend.bot.handlers.onboarding_v2.onboarding_service.get_session",
        new=AsyncMock(return_value=_session()),
    ), patch(
        "backend.bot.handlers.onboarding_v2.legacy_onboarding_service.validate_display_name",
        return_value=(True, "Minh"),
    ), patch(
        "backend.bot.handlers.onboarding_v2.legacy_onboarding_service.set_display_name",
        new=AsyncMock(),
    ) as set_display_name_mock, patch(
        "backend.bot.handlers.onboarding_v2.send_message",
        new=AsyncMock(),
    ) as send_message_mock, patch(
        "backend.bot.handlers.onboarding_v2._send_goal_question",
        new=AsyncMock(),
    ) as send_goal_mock, patch(
        "backend.bot.handlers.onboarding_v2.analytics.track",
    ) as track_mock:
        consumed = await onboarding_v2.handle_name_text_input(db, 123, user, "Minh")

    assert consumed is True
    assert user.display_name == "Minh"
    set_display_name_mock.assert_awaited_once_with(db, user.id, "Minh")
    db.flush.assert_awaited_once()
    assert send_message_mock.await_count == 1
    send_goal_mock.assert_awaited_once_with(db, 123, user)
    track_mock.assert_called_once_with("onboarding_v2_name_captured", user_id=user.id)


@pytest.mark.asyncio
async def test_handle_name_text_input_overrides_prefilled_telegram_name():
    db = MagicMock()
    db.flush = AsyncMock()
    user = _user(display_name="TelegramName")

    with patch(
        "backend.bot.handlers.onboarding_v2.onboarding_service.get_session",
        new=AsyncMock(return_value=_session()),
    ), patch(
        "backend.bot.handlers.onboarding_v2.legacy_onboarding_service.validate_display_name",
        return_value=(True, "P"),
    ), patch(
        "backend.bot.handlers.onboarding_v2.legacy_onboarding_service.set_display_name",
        new=AsyncMock(),
    ) as set_display_name_mock, patch(
        "backend.bot.handlers.onboarding_v2.send_message",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.onboarding_v2._send_goal_question",
        new=AsyncMock(),
    ):
        consumed = await onboarding_v2.handle_name_text_input(db, 123, user, "P")

    assert consumed is True
    assert user.display_name == "P"
    set_display_name_mock.assert_awaited_once_with(db, user.id, "P")


@pytest.mark.asyncio
async def test_trigger_first_twin_sends_step_3_header_before_narrative():
    db = MagicMock()
    user = _user(display_name="Minh")

    with patch("backend.bot.handlers.onboarding_v2._resolve_twin_cone", new=AsyncMock(return_value=([{"year": 1, "p10": 1, "p50": 1, "p90": 1}], 10))), \
         patch("backend.bot.handlers.onboarding_v2.send_message", new=AsyncMock()) as send_message_mock, \
         patch("backend.twin.services.twin_chart_service.render_projection_chart", return_value=b"png"), \
         patch("backend.ports.notifier.get_notifier") as get_notifier_mock, \
         patch("backend.bot.handlers.onboarding_v2.onboarding_service.mark_twin_shown", new=AsyncMock()), \
         patch("backend.bot.handlers.onboarding_v2.analytics.track"), \
         patch("backend.bot.handlers.onboarding_v2.asyncio.create_task"):
        notifier = AsyncMock()
        notifier.send_photo = AsyncMock()
        get_notifier_mock.return_value = notifier

        await onboarding_v2._trigger_first_twin(db, 123, user, demo=False)

    first_text = send_message_mock.await_args_list[0].args[1]
    assert "(3/3)" in first_text
