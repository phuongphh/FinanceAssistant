"""Hóng hớt #1062 — user-facing feed query + menu entry/actions.

CI has no database: the service runs against :class:`FakeFeedSession`,
which checks the compiled SQL carries every required filter and then
applies the same semantics in Python. Handler tests patch the service and
the Telegram transport, mirroring ``test_menu_v2``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import Select

from backend.bot.formatters import menu_formatter
from backend.models.social_buzz_item import SocialBuzzItem
from backend.services import social_buzz_service

_T0 = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)


def _item(
    title: str,
    *,
    category: str = "social",
    minutes: int = 0,
    url: str | None = None,
    is_active: bool = True,
    deleted: bool = False,
) -> SocialBuzzItem:
    return SocialBuzzItem(
        id=uuid.uuid4(),
        title=title,
        url=url,
        source_type="manual",
        category=category,
        is_active=is_active,
        created_at=_T0 + timedelta(minutes=minutes),
        deleted_at=_T0 if deleted else None,
    )


class FakeFeedSession:
    def __init__(self, items: list[SocialBuzzItem]) -> None:
        self.items = items
        self.executed = 0

    async def execute(self, stmt):
        assert isinstance(stmt, Select)
        self.executed += 1
        compiled = stmt.compile()
        text, params = str(compiled), compiled.params
        for clause in (
            "social_buzz_items.deleted_at IS NULL",
            "social_buzz_items.is_active IS true",
            "social_buzz_items.category IN",
            "ORDER BY social_buzz_items.created_at DESC",
            "LIMIT",
        ):
            assert clause in text, f"missing {clause!r} in:\n{text}"
        categories = set(params["category_1"])
        rows = [
            item
            for item in self.items
            if item.deleted_at is None and item.is_active and item.category in categories
        ]
        rows.sort(key=lambda item: item.created_at, reverse=True)
        rows = rows[: params["param_1"]]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


# ── service ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_latest_active_returns_newest_n_in_category():
    items = [_item(f"MXH {i}", minutes=i) for i in range(7)] + [
        _item("Công nghệ", category="tech", minutes=99),
    ]
    rows = await social_buzz_service.list_latest_active(
        FakeFeedSession(items), categories=("social",), limit=5
    )
    assert [row.title for row in rows] == ["MXH 6", "MXH 5", "MXH 4", "MXH 3", "MXH 2"]


@pytest.mark.asyncio
async def test_list_latest_active_skips_hidden_and_deleted_rows():
    items = [
        _item("Đang hiện", minutes=1),
        _item("Đã ẩn", minutes=2, is_active=False),
        _item("Đã xoá", minutes=3, deleted=True),
    ]
    rows = await social_buzz_service.list_latest_active(
        FakeFeedSession(items), categories=("social",), limit=5
    )
    assert [row.title for row in rows] == ["Đang hiện"]


@pytest.mark.asyncio
async def test_list_latest_active_merges_tech_and_economy():
    items = [
        _item("Kinh tế", category="economy", minutes=2),
        _item("Công nghệ", category="tech", minutes=3),
        _item("MXH", category="social", minutes=4),
    ]
    rows = await social_buzz_service.list_latest_active(
        FakeFeedSession(items), categories=("tech", "economy"), limit=5
    )
    assert [row.title for row in rows] == ["Công nghệ", "Kinh tế"]


@pytest.mark.asyncio
async def test_list_latest_active_short_circuits_without_query():
    db = FakeFeedSession([_item("MXH")])
    assert await social_buzz_service.list_latest_active(db, categories=(), limit=5) == []
    assert await social_buzz_service.list_latest_active(db, categories=("social",), limit=0) == []
    assert db.executed == 0


# ── YAML ───────────────────────────────────────────────────────────────


def test_main_menu_has_buzz_button_and_submenu():
    copy = menu_formatter._load_copy()
    callbacks = [btn["callback"] for btn in copy["main_menu"]["buttons"]]
    assert "menu:buzz" in callbacks
    buttons = copy["submenu_buzz"]["buttons"]
    assert [btn["callback"] for btn in buttons] == [
        "menu:buzz:social",
        "menu:buzz:tech_economy",
        "menu:main",
    ]
    for btn in buttons:
        assert len(btn["label"]) <= 16


def test_items_per_group_defaults_to_five():
    assert menu_formatter.get_action_int("action_buzz", "items_per_group", 99) == 5
    assert menu_formatter.get_action_int("action_buzz", "missing", 3) == 3


# ── handler ────────────────────────────────────────────────────────────


def _user():
    return SimpleNamespace(
        id="user-buzz",
        display_name="Hà",
        wealth_level="young_prof",
        get_greeting_name=lambda: "Hà",
    )


@pytest.fixture()
def telegram(monkeypatch):
    """Capture send/edit calls; ``edit_result`` controls the edit return."""
    from backend.bot.handlers import menu_handler

    calls: dict = {"sent": [], "edited": [], "edit_result": {"ok": True}}

    async def fake_send_message(**kwargs):
        calls["sent"].append(kwargs)
        return {"ok": True}

    async def fake_edit_message_text(**kwargs):
        calls["edited"].append(kwargs)
        return calls["edit_result"]

    monkeypatch.setattr(menu_handler, "send_message", fake_send_message)
    monkeypatch.setattr(menu_handler, "edit_message_text", fake_edit_message_text)
    monkeypatch.setattr(menu_handler.analytics, "track", lambda *a, **k: None)
    return calls


@pytest.fixture()
def feed(monkeypatch):
    """Patch the service with an in-memory feed keyed by category."""
    items: list[SocialBuzzItem] = []
    requested: list[tuple[tuple[str, ...], int]] = []

    async def fake_list_latest_active(db, *, categories, limit=5):
        requested.append((tuple(categories), limit))
        rows = [item for item in items if item.category in categories]
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows[:limit]

    monkeypatch.setattr(
        social_buzz_service, "list_latest_active", fake_list_latest_active
    )
    return SimpleNamespace(items=items, requested=requested)


def _link_urls(call: dict) -> list[str]:
    return [e["url"] for e in call.get("entities", []) if e["type"] == "text_link"]


@pytest.mark.asyncio
async def test_navigate_buzz_lists_both_groups_with_links(telegram, feed):
    from backend.bot.handlers import menu_handler

    feed.items.extend(
        [
            _item("Trend mì tôm", minutes=1),
            _item("Drama không link", minutes=2),
            _item("AI mới", category="tech", minutes=3, url="https://vnexpress.net/ai"),
            _item("Lãi suất giảm", category="economy", minutes=4, url="https://cafef.vn/ls"),
        ]
    )

    await menu_handler._navigate(
        db=None, user=_user(), chat_id=42, message_id=7, target="buzz"
    )

    assert feed.requested == [(("social",), 5), (("tech", "economy"), 5)]
    assert telegram["sent"] == []
    call = telegram["edited"][0]
    text = call["text"]
    assert call["parse_mode"] is None
    assert "🔥 MXH hot" in text and "📰 Tin Công nghệ/Kinh tế" in text
    assert "• Drama không link\n• Trend mì tôm" in text
    assert "• Lãi suất giảm\n• AI mới" in text
    assert "](" not in text  # markup converted to entities, never shown raw
    assert _link_urls(call) == ["https://cafef.vn/ls", "https://vnexpress.net/ai"]
    callbacks = [row[0]["callback_data"] for row in call["reply_markup"]["inline_keyboard"]]
    assert callbacks == ["menu:buzz:social", "menu:buzz:tech_economy", "menu:main"]


@pytest.mark.asyncio
async def test_navigate_buzz_empty_feed_shows_friendly_fallback(telegram, feed):
    from backend.bot.handlers import menu_handler

    await menu_handler._navigate(
        db=None, user=_user(), chat_id=42, message_id=7, target="buzz"
    )

    call = telegram["edited"][0]
    assert call["text"].startswith("🔥 HÓNG HỚT")
    assert menu_formatter.get_action_copy("action_buzz", "all_empty") in call["text"]
    assert "MXH hot" not in call["text"]
    back = call["reply_markup"]["inline_keyboard"][-1][0]
    assert back["callback_data"] == "menu:main"


@pytest.mark.asyncio
async def test_navigate_buzz_falls_back_to_send_when_edit_fails(telegram, feed):
    from backend.bot.handlers import menu_handler

    feed.items.append(_item("Trend mì tôm"))
    telegram["edit_result"] = None

    await menu_handler._navigate(
        db=None, user=_user(), chat_id=42, message_id=7, target="buzz"
    )

    assert len(telegram["sent"]) == 1
    assert "Trend mì tôm" in telegram["sent"][0]["text"]


@pytest.mark.asyncio
async def test_buzz_group_action_posts_new_message_with_back_buttons(
    telegram, feed, monkeypatch
):
    from backend.bot.handlers import menu_handler

    feed.items.append(_item("AI mới", category="tech", url="https://vnexpress.net/ai"))
    feed.items.append(_item("Trend mì tôm", category="social"))

    async def fake_answer_callback(*args, **kwargs):
        return None

    async def fake_get_user(db, telegram_id):
        return _user()

    monkeypatch.setattr(menu_handler, "answer_callback", fake_answer_callback)
    monkeypatch.setattr(menu_handler, "get_user_by_telegram_id", fake_get_user)

    handled = await menu_handler.handle_menu_callback(
        None,
        {
            "id": "cb-1",
            "data": "menu:buzz:tech_economy",
            "from": {"id": 1},
            "message": {"chat": {"id": 42}, "message_id": 7},
        },
    )

    assert handled is True
    assert telegram["edited"] == []
    call = telegram["sent"][0]
    assert call["text"] == "📰 Tin Công nghệ/Kinh tế\n• AI mới"
    assert _link_urls(call) == ["https://vnexpress.net/ai"]
    callbacks = [row[0]["callback_data"] for row in call["reply_markup"]["inline_keyboard"]]
    assert callbacks == ["menu:buzz", "menu:main"]


@pytest.mark.asyncio
async def test_buzz_group_action_empty_group_shows_placeholder(telegram, feed):
    from backend.bot.handlers import menu_handler

    await menu_handler._action_buzz_social(
        db=None, user=_user(), chat_id=42, message_id=None
    )

    text = telegram["sent"][0]["text"]
    assert text.startswith("🔥 MXH hot\n")
    assert menu_formatter.get_action_copy("action_buzz", "group_empty") in text


@pytest.mark.asyncio
async def test_back_from_buzz_returns_to_main_menu(telegram):
    from backend.bot.handlers import menu_handler

    await menu_handler._navigate(
        db=None, user=_user(), chat_id=42, message_id=7, target="main"
    )

    callbacks = [
        btn["callback_data"]
        for row in telegram["edited"][0]["reply_markup"]["inline_keyboard"]
        for btn in row
    ]
    assert "menu:buzz" in callbacks
