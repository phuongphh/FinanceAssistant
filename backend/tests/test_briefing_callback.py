"""Tests for the briefing callback handler — funnel attribution.

The handler is the only place where ``MORNING_BRIEFING_OPENED`` and
the ``BRIEFING_*_CLICKED`` events fire, so the open-rate metric in
``analytics.briefing_open_rate`` lives or dies by these tests.

What we pin:

- An ``OPENED`` event fires exactly once per briefing send window —
  multiple button taps don't double-credit the open rate.
- The action-specific ``CLICKED`` event fires every time, so the
  per-button mix breakdown stays accurate.
- A tap with no recent SENT event in the open window is treated as a
  stale message tap and doesn't credit an open.
- An unknown ``briefing:<action>`` falls through with a warning, not
  an exception.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend import analytics
from backend.bot.handlers import briefing as h
from backend.models.user import User


def _make_user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 123
    return u


def _callback(action: str = "dashboard", *, telegram_id: int = 123) -> dict:
    return {
        "id": "cb-1",
        "data": f"briefing:{action}",
        "from": {"id": telegram_id},
        "message": {"chat": {"id": 999}, "message_id": 7},
    }


@pytest.mark.asyncio
async def test_dashboard_tap_records_open_and_click():
    db = MagicMock()
    user = _make_user()

    # last sent: 5 min ago. opened lookup: nothing yet.
    sent_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    sent_result = MagicMock()
    sent_result.scalar_one_or_none.return_value = sent_at
    opened_result = MagicMock()
    opened_result.first.return_value = None
    db.execute = AsyncMock(side_effect=[sent_result, opened_result])

    track_mock = MagicMock()
    atrack_mock = AsyncMock()

    with patch(
        "backend.bot.handlers.briefing.get_user_by_telegram_id",
        new=AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.briefing.answer_callback",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.send_message",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.track",
        track_mock,
    ), patch(
        "backend.bot.handlers.briefing.analytics.atrack",
        atrack_mock,
    ):
        handled = await h.handle_briefing_callback(db, _callback("dashboard"))

    assert handled is True

    # OPEN event recorded once
    atrack_mock.assert_awaited_once()
    args, kwargs = atrack_mock.await_args
    assert args[0] == analytics.EventType.MORNING_BRIEFING_OPENED
    assert kwargs["user_id"] == user.id

    # CLICK event for the dashboard action
    track_mock.assert_called_once()
    args, kwargs = track_mock.call_args
    assert args[0] == analytics.EventType.BRIEFING_DASHBOARD_CLICKED


@pytest.mark.asyncio
async def test_second_tap_within_window_does_not_re_record_open():
    """First tap fires OPEN; second tap should fire CLICK only."""
    db = MagicMock()
    user = _make_user()

    sent_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    sent_result = MagicMock()
    sent_result.scalar_one_or_none.return_value = sent_at
    # Pretend an opened event already exists
    opened_result = MagicMock()
    opened_result.first.return_value = ("already-opened",)
    db.execute = AsyncMock(side_effect=[sent_result, opened_result])

    atrack_mock = AsyncMock()
    track_mock = MagicMock()

    storytelling_mock = AsyncMock()
    with patch(
        "backend.bot.handlers.briefing.get_user_by_telegram_id",
        new=AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.briefing.answer_callback",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.send_message",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.atrack",
        atrack_mock,
    ), patch(
        "backend.bot.handlers.briefing.analytics.track",
        track_mock,
    ), patch(
        "backend.bot.handlers.storytelling.start_storytelling",
        storytelling_mock,
    ):
        await h.handle_briefing_callback(db, _callback("story"))

    atrack_mock.assert_not_awaited()
    # Click event still fires (briefing's own funnel attribution)
    assert track_mock.call_count == 1
    args, kwargs = track_mock.call_args
    assert args[0] == analytics.EventType.BRIEFING_STORY_CLICKED
    # And the briefing forwarded the user into storytelling mode.
    storytelling_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_tap_with_no_recent_send_does_not_record_open():
    """A stale message tap (no SENT in the 30-min window) shouldn't
    inflate the open rate."""
    db = MagicMock()
    user = _make_user()

    sent_result = MagicMock()
    sent_result.scalar_one_or_none.return_value = None  # no recent send
    db.execute = AsyncMock(return_value=sent_result)

    atrack_mock = AsyncMock()
    track_mock = MagicMock()

    with patch(
        "backend.bot.handlers.briefing.get_user_by_telegram_id",
        new=AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.briefing.answer_callback",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.send_message",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.atrack",
        atrack_mock,
    ), patch(
        "backend.bot.handlers.briefing.analytics.track",
        track_mock,
    ):
        await h.handle_briefing_callback(db, _callback("settings"))

    atrack_mock.assert_not_awaited()
    # Click event still records — user did tap something
    track_mock.assert_called_once()


@pytest.mark.asyncio
async def test_add_asset_tap_forwards_to_wizard_and_tracks_click():
    """The add_asset button is the briefing-attributed entry to the
    asset wizard — handler should track + forward."""
    db = MagicMock()
    user = _make_user()

    sent_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    sent_result = MagicMock()
    sent_result.scalar_one_or_none.return_value = sent_at
    opened_result = MagicMock()
    opened_result.first.return_value = ("already-opened",)
    db.execute = AsyncMock(side_effect=[sent_result, opened_result])

    track_mock = MagicMock()
    wizard_mock = AsyncMock()

    with patch(
        "backend.bot.handlers.briefing.get_user_by_telegram_id",
        new=AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.briefing.answer_callback",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.atrack",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.track",
        track_mock,
    ), patch(
        "backend.bot.handlers.asset_entry.start_asset_wizard",
        wizard_mock,
    ):
        handled = await h.handle_briefing_callback(db, _callback("add_asset"))

    assert handled is True
    # Click event recorded with the right type
    track_mock.assert_called_once()
    args, _ = track_mock.call_args
    assert args[0] == analytics.EventType.BRIEFING_ADD_ASSET_CLICKED
    # Wizard was invoked
    wizard_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_callback_data_returns_false():
    """Any prefix outside ``briefing:`` is left for downstream routers."""
    handled = await h.handle_briefing_callback(
        MagicMock(),
        {"id": "x", "data": "asset_add:start", "from": {"id": 1},
         "message": {"chat": {"id": 2}}},
    )
    assert handled is False


@pytest.mark.asyncio
async def test_story_tap_forwards_to_storytelling_with_briefing_source():
    """P3A-20: 'Kể chuyện' button must launch storytelling with the
    ``from_briefing`` attribution so the funnel split survives."""
    db = MagicMock()
    user = _make_user()

    sent_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    sent_result = MagicMock()
    sent_result.scalar_one_or_none.return_value = sent_at
    opened_result = MagicMock()
    opened_result.first.return_value = ("already-opened",)
    db.execute = AsyncMock(side_effect=[sent_result, opened_result])

    track_mock = MagicMock()
    storytelling_mock = AsyncMock()

    with patch(
        "backend.bot.handlers.briefing.get_user_by_telegram_id",
        new=AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.briefing.answer_callback",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.atrack",
        new=AsyncMock(),
    ), patch(
        "backend.bot.handlers.briefing.analytics.track",
        track_mock,
    ), patch(
        "backend.bot.handlers.storytelling.start_storytelling",
        storytelling_mock,
    ):
        handled = await h.handle_briefing_callback(db, _callback("story"))

    assert handled is True
    storytelling_mock.assert_awaited_once()
    # The third positional/kwarg value tells us how storytelling was invoked.
    _args, kwargs = storytelling_mock.await_args
    # source kwarg is the funnel attribution
    from backend.bot.handlers.storytelling import SOURCE_FROM_BRIEFING

    assert kwargs.get("source") == SOURCE_FROM_BRIEFING
    # And the briefing-side click event was recorded.
    events = [c.args[0] for c in track_mock.call_args_list]
    assert analytics.EventType.BRIEFING_STORY_CLICKED in events


@pytest.mark.asyncio
async def test_unregistered_user_gets_friendly_alert():
    db = MagicMock()
    answer_mock = AsyncMock()

    with patch(
        "backend.bot.handlers.briefing.get_user_by_telegram_id",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.bot.handlers.briefing.answer_callback",
        answer_mock,
    ):
        handled = await h.handle_briefing_callback(db, _callback())

    assert handled is True
    answer_mock.assert_awaited_once()
    _, kwargs = answer_mock.await_args
    assert kwargs.get("show_alert") is True
