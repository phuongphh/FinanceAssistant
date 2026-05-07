from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.jobs.reminder_scheduler_job import _should_send_reminders_now
from backend.models.user import User
from backend.profile.handlers.profile_menu import (
    handle_profile_callback,
    handle_profile_view,
    notification_keyboard,
    parse_hhmm,
    render_profile,
    sanitize_display_name,
)
from backend.profile.models.user_profile import UserProfile
from backend.profile.services.stats_aggregator import ProfileStatsAggregator
from backend.profile.services.wealth_level_mapper import WealthLevelMapper


def _scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


def _scalars(values):
    scalars = MagicMock()
    scalars.all.return_value = values
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def test_wealth_level_starter():
    level = WealthLevelMapper().get_level(Decimal("15000000"))
    assert level["name_vn"] == "Khởi Đầu"


def test_wealth_level_boundary_30tr():
    level = WealthLevelMapper().get_level(Decimal("30000000"))
    assert level["name_vn"] == "Trẻ Năng Động"


def test_wealth_progress_halfway_to_next():
    progress = WealthLevelMapper().get_progress_to_next(Decimal("15000000"))
    assert 49 <= progress["progress_pct"] <= 51
    assert progress["next_level_name"] == "Trẻ Năng Động"


@pytest.mark.asyncio
async def test_aggregate_new_user_defaults_gracefully():
    user = User()
    user.id = uuid.uuid4()
    user.created_at = datetime.now(timezone.utc)
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.execute = AsyncMock(side_effect=[
        _scalar(0),  # asset types
        _scalar(0),  # transactions total
        _scalar(0),  # transactions month
        _scalar(0),  # goals active
        _scalar(0),  # goals completed
        _scalar(0),  # briefing reads
        _scalars([]),  # activity days
        _scalar(None),  # first snapshot
    ])

    with patch(
        "backend.profile.services.stats_aggregator.net_worth_calculator.calculate",
        AsyncMock(return_value=SimpleNamespace(total=Decimal("0"))),
    ):
        stats = await ProfileStatsAggregator().aggregate(db, user.id)

    assert stats["account_age_days"] == 0
    assert stats["wealth_level"]["name_vn"] == "Khởi Đầu"
    assert stats["current_streak"] == 1
    assert stats["asset_types_count"] == 0


@pytest.mark.asyncio
async def test_streak_breaks_after_gap():
    aggregator = ProfileStatsAggregator()
    with patch.object(aggregator, "_activity_days", AsyncMock(return_value=[])):
        assert await aggregator._compute_streak(MagicMock(), uuid.uuid4()) == 1


def test_render_profile_includes_vn_level_and_stats():
    profile = UserProfile(user_id=uuid.uuid4(), display_name="Phương")
    user = User()
    user.id = profile.user_id
    user.display_name = "Telegram Phương"
    stats = {
        "account_age_days": 12,
        "net_worth": Decimal("300000000"),
        "wealth_level": WealthLevelMapper().get_level(Decimal("300000000")),
        "wealth_progress": WealthLevelMapper().get_progress_to_next(
            Decimal("300000000")
        ),
        "asset_types_count": 3,
        "transaction_count_total": 40,
        "transaction_count_this_month": 8,
        "goals_active": 2,
        "goals_completed": 1,
        "briefing_read_count": 5,
        "current_streak": 4,
        "net_worth_change_pct": 12.5,
    }

    text = render_profile(profile, user, stats)

    assert "Phương" in text
    assert "💎" in text
    assert "Trung Lưu Vững" in text
    assert "Tinh Hoa" in text
    assert "8" in text


@pytest.mark.asyncio
async def test_handle_profile_view_degrades_when_profile_storage_fails(monkeypatch):
    expired = False

    class RollbackExpiringUser:
        id = uuid.uuid4()
        briefing_enabled = True
        briefing_time = time(7, 0)

        @property
        def display_name(self):
            if expired:
                raise AssertionError("user ORM object was accessed after rollback")
            return "Bé Tiền Test"

    user = RollbackExpiringUser()

    async def expire_on_rollback():
        nonlocal expired
        expired = True

    db = MagicMock()
    db.execute = AsyncMock(side_effect=SQLAlchemyError("missing user_profiles"))
    db.rollback = AsyncMock(side_effect=expire_on_rollback)
    sent: dict = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(
        "backend.profile.handlers.profile_menu.send_message",
        fake_send_message,
    )

    await handle_profile_view(db, chat_id=42, user=user)

    assert sent["chat_id"] == 42
    assert "Profile của Bé Tiền Test" in sent["text"]
    assert "alembic upgrade head" in sent["text"]
    assert sent["reply_markup"]["inline_keyboard"] == [
        [{"text": "◀️ Quay lại", "callback_data": "menu:main"}]
    ]
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_profile_view_degrades_when_stats_fail(monkeypatch):
    user = User()
    user.id = uuid.uuid4()
    user.display_name = "Bé Tiền Test"

    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar(None))
    sent: dict = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    async def fake_aggregate(self, db, user_id):
        raise RuntimeError("stats backend down")

    monkeypatch.setattr(
        "backend.profile.handlers.profile_menu.send_message",
        fake_send_message,
    )
    monkeypatch.setattr(
        "backend.profile.handlers.profile_menu.ProfileStatsAggregator.aggregate",
        fake_aggregate,
    )

    await handle_profile_view(db, chat_id=42, user=user)

    assert "Profile của Bé Tiền Test" in sent["text"]
    assert "chế độ an toàn" in sent["text"]
    assert len(sent["reply_markup"]["inline_keyboard"]) == 3


def test_sanitize_display_name_validates_and_strips_at():
    assert sanitize_display_name("@Phương 💚\x00") == ("Phương 💚", None)
    assert sanitize_display_name("   ")[1] == "Tên không được trống."
    assert sanitize_display_name("x" * 51)[1] == (
        "Tên dài quá! Tối đa 50 ký tự nhé."
    )


def test_parse_hhmm_validation():
    assert parse_hhmm("7:05") == time(7, 5)
    assert parse_hhmm("25:99") is None
    assert parse_hhmm("bad") is None


def test_notification_keyboard_reflects_status_and_times():
    profile = UserProfile(user_id=uuid.uuid4())
    profile.briefing_enabled = False
    profile.briefing_time = time(8, 0)
    profile.reminder_enabled = True
    profile.reminder_time = time(9, 30)

    keyboard = notification_keyboard(profile)
    buttons = [button[0]["text"] for button in keyboard["inline_keyboard"][:4]]

    assert "🔕 Tắt" in buttons[0]
    assert "08:00" in buttons[1]
    assert "✅ Bật" in buttons[2]
    assert "09:30" in buttons[3]




@pytest.mark.asyncio
async def test_preset_briefing_time_callback_accepts_colon_value(monkeypatch):
    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 12345
    user.briefing_time = time(7, 0)
    profile = UserProfile(user_id=user.id)
    profile.briefing_time = time(7, 0)
    profile.briefing_enabled = True
    profile.reminder_enabled = True
    profile.reminder_time = time(9, 0)
    db = MagicMock()
    db.flush = AsyncMock()
    edited: dict = {}

    async def fake_get_user(db, telegram_id):
        assert telegram_id == 12345
        return user

    async def fake_get_or_create_profile(db, user_id):
        assert user_id == user.id
        return profile

    async def fake_answer_callback(*args, **kwargs):
        assert kwargs.get("text") != "Giờ không hợp lệ."

    async def fake_edit_message_text(**kwargs):
        edited.update(kwargs)

    monkeypatch.setattr(
        "backend.profile.handlers.profile_menu._get_user_by_telegram_id",
        fake_get_user,
    )
    monkeypatch.setattr(
        "backend.profile.handlers.profile_menu.get_or_create_profile",
        fake_get_or_create_profile,
    )
    monkeypatch.setattr(
        "backend.profile.handlers.profile_menu.answer_callback",
        fake_answer_callback,
    )
    monkeypatch.setattr(
        "backend.profile.handlers.profile_menu.edit_message_text",
        fake_edit_message_text,
    )

    handled = await handle_profile_callback(
        db,
        {
            "id": "cb-1",
            "data": "profile:time:briefing:08:00",
            "from": {"id": 12345},
            "message": {"chat": {"id": 42}, "message_id": 99},
        },
    )

    assert handled is True
    assert profile.briefing_time == time(8, 0)
    assert user.briefing_time == time(8, 0)
    assert "08:00" in edited["text"]
    db.flush.assert_awaited_once()


def test_reminder_profile_settings_gate_delivery_time():
    profile = UserProfile(user_id=uuid.uuid4())
    profile.reminder_enabled = True
    profile.reminder_time = time(8, 0)

    assert _should_send_reminders_now(
        profile,
        now=datetime(2026, 5, 7, 8, 10, tzinfo=timezone.utc),
    ) is True
    assert _should_send_reminders_now(
        profile,
        now=datetime(2026, 5, 7, 8, 15, tzinfo=timezone.utc),
    ) is False

    profile.reminder_enabled = False
    assert _should_send_reminders_now(
        profile,
        now=datetime(2026, 5, 7, 8, 5, tzinfo=timezone.utc),
    ) is False
