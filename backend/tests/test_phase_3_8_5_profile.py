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
from backend.models.credit_card import CreditCard
from backend.profile.handlers.profile_menu import (
    _expense_source_options,
    _resolve_source_label,
    handle_profile_callback,
    handle_profile_view,
    notification_keyboard,
    parse_hhmm,
    render_glossary,
    render_profile,
    sanitize_display_name,
)
from backend.profile.handlers import profile_menu as profile_menu_module
from backend.profile.models.user_profile import UserProfile
from backend.wealth.models.asset import Asset
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
    # 5 rows: [edit_name, edit_age] + [notifications] + [glossary]
    # + [default_expense_source] + [back]
    assert len(sent["reply_markup"]["inline_keyboard"]) == 5


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


def test_render_glossary_includes_all_six_terms():
    text = render_glossary()

    # Title + intro
    assert "Giải thích các mục" in text
    assert "quay lại Profile" in text  # intro hints at the back button

    # All six ambiguous terms must be explained
    assert "Báo cáo sáng" in text
    assert "Nhắc định kỳ" in text
    assert "Hành trình tài sản" in text
    assert "Thay đổi tài sản" in text
    assert "Loại tài sản" in text
    assert "Chuỗi hoạt động" in text

    # Key clarifying details users would otherwise miss
    assert "ngày đầu tiên" in text  # net-worth-change baseline
    assert "Khởi Đầu" in text and "Tinh Hoa" in text  # wealth levels named


def test_render_glossary_separates_entries_with_blank_lines():
    text = render_glossary()

    # Each entry should be visually separated by a blank line so the
    # screen reads as standalone cards on mobile.
    assert "\n\n🌅" in text or text.startswith("🌅") or "\n\n*" in text
    # Joining via "_join_entries" inserts an empty string between entries,
    # which becomes a blank line when joined with "\n".
    blocks = [block for block in text.split("\n\n") if block.strip()]
    # Title + intro + 6 entries = 8 standalone blocks
    assert len(blocks) == 8


def test_glossary_keyboard_has_single_back_button():
    keyboard = profile_menu_module.glossary_keyboard()

    rows = keyboard["inline_keyboard"]
    assert len(rows) == 1
    assert len(rows[0]) == 1
    back = rows[0][0]
    assert "Quay lại Profile" in back["text"]
    # Reuses the existing profile:view callback to re-render the Profile
    # in place; no separate "back from glossary" route needed.
    assert back["callback_data"] == "profile:view"


@pytest.mark.asyncio
async def test_glossary_callback_edits_message_with_glossary_text(monkeypatch):
    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 12345
    profile = UserProfile(user_id=user.id)
    db = MagicMock()
    db.flush = AsyncMock()
    edited: dict = {}

    async def fake_get_user(db, telegram_id):
        return user

    async def fake_get_or_create_profile(db, user_id):
        return profile

    async def fake_answer_callback(*args, **kwargs):
        return None

    async def fake_edit_message_text(**kwargs):
        edited.update(kwargs)

    async def fake_send_message(**kwargs):  # pragma: no cover — fallback path
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
    monkeypatch.setattr(
        "backend.profile.handlers.profile_menu.send_message",
        fake_send_message,
    )

    handled = await handle_profile_callback(
        db,
        {
            "id": "cb-glossary",
            "data": "profile:glossary",
            "from": {"id": 12345},
            "message": {"chat": {"id": 42}, "message_id": 99},
        },
    )

    assert handled is True
    assert edited["chat_id"] == 42
    assert edited["message_id"] == 99
    assert "Giải thích các mục" in edited["text"]
    assert edited["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == (
        "profile:view"
    )


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


@pytest.mark.asyncio
async def test_expense_source_options_include_all_supported_types():
    user_id = uuid.uuid4()
    db = MagicMock()

    card = CreditCard(user_id=user_id, bank_name="VCB", closing_date=1)
    card.id = uuid.uuid4()
    card.created_at = datetime.now(timezone.utc)

    bank_asset = Asset(
        user_id=user_id,
        asset_type="cash",
        subtype="bank_checking",
        name="Techcombank",
        initial_value=Decimal("0"),
        current_value=Decimal("0"),
        acquired_at=datetime.now(timezone.utc).date(),
    )
    bank_asset.id = uuid.uuid4()
    bank_asset.is_active = True
    bank_asset.created_at = datetime.now(timezone.utc)

    wallet_asset = Asset(
        user_id=user_id,
        asset_type="cash",
        subtype="momo",
        name="MoMo Cá nhân",
        initial_value=Decimal("0"),
        current_value=Decimal("0"),
        acquired_at=datetime.now(timezone.utc).date(),
    )
    wallet_asset.id = uuid.uuid4()
    wallet_asset.is_active = True
    wallet_asset.created_at = datetime.now(timezone.utc)

    db.execute = AsyncMock(
        side_effect=[_scalars([card]), _scalars([bank_asset, wallet_asset])]
    )
    options = await _expense_source_options(user_id, db)

    assert ("cash", "Tiền mặt") in options
    assert (f"credit_card:{card.id}", "Thẻ tín dụng [VCB]") in options
    assert (f"bank_account:{bank_asset.id}", "Tài khoản thanh toán [Techcombank]") in options
    assert (f"e_wallet:{wallet_asset.id}", "Ví điện tử [MoMo Cá nhân]") in options


def test_resolve_source_label_returns_fallback_for_missing_or_unknown():
    options = [("cash", "Tiền mặt"), ("credit_card:1", "Thẻ tín dụng [VCB]")]
    assert _resolve_source_label(options, None) == "Chưa cài đặt"
    assert _resolve_source_label(options, "unknown") == "Chưa cài đặt"
    assert _resolve_source_label(options, "cash") == "Tiền mặt"


@pytest.mark.asyncio
async def test_default_expense_source_callback_routes_to_panel(monkeypatch):
    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 12345
    profile = UserProfile(user_id=user.id)
    db = MagicMock()

    monkeypatch.setattr(
        profile_menu_module,
        "_get_user_by_telegram_id",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        profile_menu_module,
        "get_or_create_profile",
        AsyncMock(return_value=profile),
    )
    render = AsyncMock()
    monkeypatch.setattr(profile_menu_module, "_render_default_expense_source", render)
    monkeypatch.setattr(profile_menu_module, "answer_callback", AsyncMock())

    handled = await handle_profile_callback(
        db,
        {
            "id": "cb-default",
            "data": "profile:default_expense_source",
            "from": {"id": 12345},
            "message": {"chat": {"id": 42}, "message_id": 10},
        },
    )

    assert handled is True
    render.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_default_expense_source_updates_profile_and_sends_confirm(monkeypatch):
    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 12345
    profile = UserProfile(user_id=user.id)
    db = MagicMock()
    db.flush = AsyncMock()

    monkeypatch.setattr(
        profile_menu_module,
        "_get_user_by_telegram_id",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        profile_menu_module,
        "get_or_create_profile",
        AsyncMock(return_value=profile),
    )
    monkeypatch.setattr(
        profile_menu_module,
        "_expense_source_options",
        AsyncMock(return_value=[("cash", "Tiền mặt")]),
    )
    monkeypatch.setattr(profile_menu_module, "_render_default_expense_source", AsyncMock())
    send = AsyncMock()
    monkeypatch.setattr(profile_menu_module, "send_message", send)
    monkeypatch.setattr(profile_menu_module, "answer_callback", AsyncMock())

    handled = await handle_profile_callback(
        db,
        {
            "id": "cb-set",
            "data": "profile:set_default_expense_source:cash",
            "from": {"id": 12345},
            "message": {"chat": {"id": 42}, "message_id": 11},
        },
    )

    assert handled is True
    assert profile.default_expense_source == "cash"
    db.flush.assert_awaited_once()
    assert any(
        "Đã đổi nguồn chi tiêu thường xuyên" in call.kwargs.get("text", "")
        for call in send.await_args_list
    )


@pytest.mark.asyncio
async def test_set_default_expense_source_accepts_short_token_and_saves_real_key(monkeypatch):
    user = User()
    user.id = uuid.uuid4()
    profile = UserProfile(user_id=user.id)
    db = MagicMock()
    db.flush = AsyncMock()

    card_key = f"credit_card:{uuid.uuid4()}"
    monkeypatch.setattr(
        profile_menu_module,
        "_expense_source_options",
        AsyncMock(return_value=[("cash", "Tiền mặt"), (card_key, "Thẻ tín dụng [VCB]")]),
    )
    monkeypatch.setattr(profile_menu_module, "_render_default_expense_source", AsyncMock())
    monkeypatch.setattr(profile_menu_module, "send_message", AsyncMock())

    await profile_menu_module._set_default_expense_source(
        db,
        chat_id=42,
        message_id=88,
        user=user,
        profile=profile,
        source_key="opt1",
    )

    assert profile.default_expense_source == card_key
    db.flush.assert_awaited_once()


def test_decode_source_token_handles_valid_invalid_and_legacy_values():
    options = [
        ("cash", "Tiền mặt"),
        ("credit_card:abc", "Thẻ tín dụng [VCB]"),
    ]
    assert profile_menu_module._decode_source_token("opt0", options) == "cash"
    assert profile_menu_module._decode_source_token("opt1", options) == "credit_card:abc"
    assert profile_menu_module._decode_source_token("opt99", options) == "opt99"
    assert profile_menu_module._decode_source_token("optx", options) == "optx"
    assert (
        profile_menu_module._decode_source_token("credit_card:abc", options)
        == "credit_card:abc"
    )


@pytest.mark.asyncio
async def test_render_default_expense_source_options_uses_short_callback_tokens(monkeypatch):
    user = User()
    user.id = uuid.uuid4()
    long_key = f"credit_card:{uuid.uuid4()}"

    monkeypatch.setattr(
        profile_menu_module,
        "_expense_source_options",
        AsyncMock(return_value=[("cash", "Tiền mặt"), (long_key, "Thẻ tín dụng [VCB]")]),
    )
    edit = AsyncMock()
    monkeypatch.setattr(profile_menu_module, "edit_message_text", edit)

    await profile_menu_module._render_default_expense_source_options(
        MagicMock(), chat_id=42, message_id=99, user=user
    )

    rows = edit.await_args.kwargs["reply_markup"]["inline_keyboard"]
    callback_values = [row[0]["callback_data"] for row in rows[:-1]]
    assert callback_values == [
        "profile:set_default_expense_source:opt0",
        "profile:set_default_expense_source:opt1",
    ]
    assert all(len(value) <= 64 for value in callback_values)

@pytest.mark.asyncio
async def test_expense_source_options_sorted_by_type_then_name(monkeypatch):
    user_id = uuid.uuid4()

    card_b = SimpleNamespace(id=uuid.uuid4(), bank_name="ZBank")
    card_a = SimpleNamespace(id=uuid.uuid4(), bank_name="ACB")
    bank_b = SimpleNamespace(id=uuid.uuid4(), subtype="bank_account", name="Vietcombank", is_active=True)
    bank_a = SimpleNamespace(id=uuid.uuid4(), subtype="bank_checking", name="ACB", is_active=True)
    wallet_b = SimpleNamespace(id=uuid.uuid4(), subtype="e_wallet", name="ZaloPay", is_active=True)
    wallet_a = SimpleNamespace(id=uuid.uuid4(), subtype="momo", name="MoMo", is_active=True)

    class _FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def all(self):
            return self._items

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_FakeResult([card_b, card_a]), _FakeResult([bank_b, bank_a, wallet_b, wallet_a])])

    options = await profile_menu_module._expense_source_options(user_id, db)

    assert options == [
        ("cash", "Tiền mặt"),
        (f"bank_account:{bank_a.id}", "Tài khoản thanh toán [ACB]"),
        (f"bank_account:{bank_b.id}", "Tài khoản thanh toán [Vietcombank]"),
        (f"credit_card:{card_a.id}", "Thẻ tín dụng [ACB]"),
        (f"credit_card:{card_b.id}", "Thẻ tín dụng [ZBank]"),
        (f"e_wallet:{wallet_a.id}", "Ví điện tử [MoMo]"),
        (f"e_wallet:{wallet_b.id}", "Ví điện tử [ZaloPay]"),
    ]
