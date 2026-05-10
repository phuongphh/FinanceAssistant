from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers.morning_briefing_command import send_morning_briefing_now
from backend.briefing.morning_briefing import EnrichedBriefingResult
from backend.models.user import User
from backend.wealth.ladder import WealthLevel


@pytest.mark.asyncio
async def test_manual_morning_briefing_uses_entities_and_does_not_mark_scheduled_sent():
    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 999
    user.display_name = "Minh"
    result = EnrichedBriefingResult(
        text="🌤️ Chào buổi sáng, Minh!",
        level=WealthLevel.STARTER,
        is_empty_state=False,
        sections={},
    )
    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value={"ok": True})

    # Inject a valid emoji map so the briefing pipeline produces entities.
    # Production YAML keeps animation_id commented out until real Telegram
    # custom_emoji_ids are harvested (see content/emoji_animation_map.yaml).
    fake_emoji_map = {
        "partly_sunny": {
            "static": "🌤️",
            "animation_id": "test-sun",
            "contexts": ["briefing"],
        },
    }
    with patch(
        "backend.bot.handlers.morning_briefing_command.render_enriched_morning_briefing",
        new_callable=AsyncMock,
        return_value=result,
    ), patch(
        "backend.bot.handlers.morning_briefing_command.get_notifier",
        return_value=notifier,
    ), patch(
        "backend.bot.utils.emoji_animation.load_emoji_animation_map",
        return_value=fake_emoji_map,
    ), patch(
        "backend.bot.handlers.morning_briefing_command.analytics.atrack",
        new_callable=AsyncMock,
    ) as mock_track:
        sent = await send_morning_briefing_now(MagicMock(), chat_id=123, user=user)

    assert sent is True
    notifier.send_message.assert_awaited_once()
    _, kwargs = notifier.send_message.await_args
    assert kwargs["parse_mode"] is None
    assert kwargs["entities"]
    mock_track.assert_awaited_once()
    assert mock_track.await_args.args[0] == "morning_briefing_requested"
