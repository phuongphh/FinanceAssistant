"""Test that morning_report_service routes through the Notifier port.

The point of the B3 refactor is that this test can exist at all —
before it, the service imported ``send_message`` / ``send_photo``
directly from ``telegram_service`` and you couldn't exercise it
without mocking HTTP.

Focus here is the send-dispatch logic (no-assets branch, short vs
long caption branch). The actual content generation
(``build_morning_report`` / ``_build_greeting``) has its own tests.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.user import User
from backend.services import morning_report_service
from backend.tests._fakes.notifier import FakeNotifier


def _make_user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 777
    u.display_name = "Minh"
    return u


@pytest.mark.asyncio
async def test_no_assets_sends_single_message():
    user = _make_user()
    fake = FakeNotifier()

    with patch(
        "backend.services.morning_report_service.get_notifier",
        return_value=fake,
    ), patch(
        "backend.services.morning_report_service.build_morning_report",
        new_callable=AsyncMock,
        return_value=(b"", "", False),
    ):
        ok = await morning_report_service.send_morning_report(MagicMock(), user)

    assert ok is True
    # One message (the no-assets nudge), no photo.
    assert len(fake.messages) == 1
    assert len(fake.photos) == 0
    assert fake.messages[0].chat_id == 777
    assert "Bạn chưa có tài sản" in fake.messages[0].text


@pytest.mark.asyncio
async def test_short_caption_sends_photo_with_buttons():
    user = _make_user()
    fake = FakeNotifier()
    short_summary = "Tổng tài sản: 10,000,000 đ"

    with patch(
        "backend.services.morning_report_service.get_notifier",
        return_value=fake,
    ), patch(
        "backend.services.morning_report_service.build_morning_report",
        new_callable=AsyncMock,
        return_value=(b"PNGDATA", short_summary, True),
    ):
        await morning_report_service.send_morning_report(MagicMock(), user)

    # Single photo carries the whole greeting + summary + buttons.
    assert len(fake.messages) == 0
    assert len(fake.photos) == 1
    photo = fake.photos[0]
    assert photo.chat_id == 777
    assert photo.photo == b"PNGDATA"
    assert short_summary in photo.caption
    assert photo.reply_markup is not None
    assert "inline_keyboard" in photo.reply_markup


@pytest.mark.asyncio
async def test_long_caption_splits_into_three_sends():
    """Telegram caption cap is 1024 chars. When our caption would
    exceed that, the service splits into: greeting text → bare photo
    → summary message with the action buttons. Order matters for
    rendering."""
    user = _make_user()
    fake = FakeNotifier()
    long_summary = "x" * 1200  # forces the over-1024 branch

    with patch(
        "backend.services.morning_report_service.get_notifier",
        return_value=fake,
    ), patch(
        "backend.services.morning_report_service.build_morning_report",
        new_callable=AsyncMock,
        return_value=(b"PNGDATA", long_summary, True),
    ):
        await morning_report_service.send_morning_report(MagicMock(), user)

    # Two messages (greeting + summary) and one photo, in order.
    assert len(fake.messages) == 2
    assert len(fake.photos) == 1
    # Ordering: greeting → photo → summary
    assert fake.log[0] is fake.messages[0]
    assert fake.log[1] is fake.photos[0]
    assert fake.log[2] is fake.messages[1]
    # Buttons only on the summary, not the greeting or the photo.
    assert fake.messages[0].reply_markup is None
    assert fake.photos[0].reply_markup is None
    assert fake.messages[1].reply_markup is not None


@pytest.mark.asyncio
async def test_no_telegram_service_imported():
    """Smoke: the module should no longer import from telegram_service
    at the top level — that's the whole point of going through the
    Notifier port."""
    source = (
        __import__("pathlib").Path(morning_report_service.__file__).read_text()
    )
    # Allow references inside comments / docstrings, but no real import.
    assert "from backend.services.telegram_service import" not in source
