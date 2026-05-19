"""Tests for the Phase 4.3 Twin habit-loop wiring.

Covers the three integration points where the storyboard surfaces
reach Telegram:

- ``briefing:open_twin`` callback hands off to ``send_twin_current``
  and records the funnel click.
- ``on_demand_recompute._notify`` renders the push from
  ``content/twin_copy.yaml`` (no hardcoded VN strings) with the
  causality+action button row.
- ``first_time_view.mark_story_completed`` writes the right
  ``TwinViewEvent`` so the 30-day reshow gate trips for both
  Telegram preamble and Mini App carousel.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend import analytics
from backend.bot.handlers import briefing as briefing_handler
from backend.models.user import User
from backend.twin.flows import first_time_view
from backend.twin.services import on_demand_recompute


def _user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 555
    return u


def _briefing_callback(action: str = "open_twin") -> dict:
    return {
        "id": "cb-twin",
        "data": f"briefing:{action}",
        "from": {"id": 555},
        "message": {"chat": {"id": 42}, "message_id": 1},
    }


@pytest.mark.asyncio
async def test_open_twin_callback_forwards_and_tracks_click():
    """The briefing's full-width Twin button must (a) fire
    ``BRIEFING_OPEN_TWIN_CLICKED`` and (b) drop the user straight into
    ``send_twin_current`` — that's the habit-loop trigger moment."""
    db = MagicMock()
    user = _user()

    sent_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    sent_result = MagicMock()
    sent_result.scalar_one_or_none.return_value = sent_at
    opened_result = MagicMock()
    opened_result.first.return_value = ("already-opened",)
    db.execute = AsyncMock(side_effect=[sent_result, opened_result])

    track_mock = MagicMock()
    send_twin_mock = AsyncMock()

    with patch(
        "backend.bot.handlers.briefing.get_user_by_telegram_id",
        new=AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.briefing.answer_callback", new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.atrack", new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.track", track_mock,
    ), patch(
        "backend.bot.handlers.twin_handler.send_twin_current", send_twin_mock,
    ):
        handled = await briefing_handler.handle_briefing_callback(
            db, _briefing_callback("open_twin")
        )

    assert handled is True
    send_twin_mock.assert_awaited_once()
    _args, kwargs = send_twin_mock.await_args
    assert kwargs.get("chat_id") == 42
    assert kwargs.get("user") is user
    events = [c.args[0] for c in track_mock.call_args_list]
    assert analytics.EventType.BRIEFING_OPEN_TWIN_CLICKED in events


@pytest.mark.asyncio
async def test_notify_renders_copy_from_yaml_for_positive_delta():
    """Push text and direction word come from ``twin_copy.yaml`` — a
    regression to hardcoded VN strings here would re-introduce the
    CLAUDE.md violation."""
    notifier = AsyncMock()
    notifier.send_message = AsyncMock()
    on_demand_recompute._habit_loop_copy.cache_clear()

    with patch(
        "backend.twin.services.on_demand_recompute.get_notifier",
        return_value=notifier,
    ):
        await on_demand_recompute._notify(
            chat_id=99, delta_abs=Decimal("100000"), delta_pct=Decimal("3.50")
        )

    notifier.send_message.assert_awaited_once()
    _args, kwargs = notifier.send_message.await_args
    text = kwargs["text"]
    copy = on_demand_recompute._habit_loop_copy()
    assert copy["push_direction_up"] in text
    assert "3.50" in text
    # Keyboard row carries the two habit-loop callbacks.
    rows = kwargs["reply_markup"]["inline_keyboard"]
    assert len(rows) == 1 and len(rows[0]) == 2
    cb = {btn["callback_data"] for btn in rows[0]}
    assert cb == {"twin:causality", "twin:action"}


@pytest.mark.asyncio
async def test_notify_uses_down_direction_for_negative_delta():
    notifier = AsyncMock()
    notifier.send_message = AsyncMock()
    on_demand_recompute._habit_loop_copy.cache_clear()

    with patch(
        "backend.twin.services.on_demand_recompute.get_notifier",
        return_value=notifier,
    ):
        await on_demand_recompute._notify(
            chat_id=1, delta_abs=Decimal("-50000"), delta_pct=Decimal("-1.20")
        )

    text = notifier.send_message.await_args.kwargs["text"]
    copy = on_demand_recompute._habit_loop_copy()
    assert copy["push_direction_down"] in text
    # Absolute value rendered — no leading minus on the percentage.
    assert "1.20" in text


@pytest.mark.asyncio
async def test_mark_story_completed_writes_event_and_flushes():
    """The 30-day reshow gate keys off ``story_completed`` events;
    Telegram preamble must log one so subsequent opens stay quiet."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    user_id = uuid.uuid4()

    await first_time_view.mark_story_completed(
        db, user_id, surface="telegram", screen_id="telegram_preamble"
    )

    db.add.assert_called_once()
    event = db.add.call_args.args[0]
    assert event.user_id == user_id
    assert event.event_type == "story_completed"
    assert event.screen_id == "telegram_preamble"
    assert event.flow_mode == "compact"
    assert event.metadata_ == {"surface": "telegram"}
    db.flush.assert_awaited_once()


def test_habit_loop_copy_has_all_required_keys():
    """Smoke test that the YAML keys ``_notify`` and the handler depend
    on actually exist — a typo in the YAML would otherwise show up as
    silently fallback English text in production."""
    on_demand_recompute._habit_loop_copy.cache_clear()
    copy = on_demand_recompute._habit_loop_copy()
    for key in (
        "prompt",
        "button_causality",
        "button_action",
        "push_direction_up",
        "push_direction_down",
        "push_text",
        "first_time_intro",
    ):
        assert key in copy, f"missing habit_loop.{key}"
    # ``push_text`` must accept the three named placeholders.
    rendered = copy["push_text"].format(
        direction=copy["push_direction_up"], pct="1.23", causality="X"
    )
    assert "1.23" in rendered
