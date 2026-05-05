"""Tests for Phase 3.6 menu — YAML schema + formatter + callback router.

Three concerns covered:
  1. YAML structure (every menu has the four wealth-level intros, every
     button has a label + callback under Telegram's limit).
  2. Formatter output shape (text + dict-based inline keyboard).
  3. Callback router routes / declines correctly.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.bot.formatters import menu_formatter
from backend.bot.formatters.menu_formatter import (
    DEFAULT_LEVEL,
    VALID_LEVELS,
    back_to_main_keyboard,
    format_main_menu,
    format_submenu,
    known_categories,
)


# Telegram's hard limit on callback_data — we mirror this constant
# rather than importing from another module so this test fails loudly
# if either side drifts.
CALLBACK_DATA_MAX_BYTES = 64


def _all_buttons():
    """Yield every (menu_key, button_dict) across the YAML."""
    copy = menu_formatter._load_copy()
    for menu_key, cfg in copy.items():
        for btn in cfg.get("buttons", []):
            yield menu_key, btn


# ============================================================
# YAML schema invariants — Story S1 acceptance criteria
# ============================================================


class TestYamlSchema:
    def test_yaml_loads_without_error(self):
        copy = menu_formatter._load_copy()
        assert isinstance(copy, dict)
        assert "main_menu" in copy

    def test_main_menu_has_five_categories(self):
        copy = menu_formatter._load_copy()
        buttons = copy["main_menu"]["buttons"]
        assert len(buttons) == 5

    def test_main_menu_buttons_route_to_known_categories(self):
        copy = menu_formatter._load_copy()
        cats = set(known_categories())
        for btn in copy["main_menu"]["buttons"]:
            cat = btn["callback"].split(":")[1]
            assert cat in cats, f"Main menu button points to unknown category: {cat}"

    def test_all_five_submenus_exist(self):
        cats = known_categories()
        expected = {"assets", "expenses", "cashflow", "goals", "market"}
        assert expected == set(cats)

    def test_all_adaptive_sections_have_four_levels(self):
        """Every ``intro`` block (and the main menu's ``title``) must
        include all four wealth-level keys so Epic 2's adaptive lookup
        can never miss.
        """
        copy = menu_formatter._load_copy()

        # main_menu.title is also adaptive (only place that varies title).
        assert set(copy["main_menu"]["title"].keys()) == VALID_LEVELS
        assert set(copy["main_menu"]["intro"].keys()) == VALID_LEVELS

        for cat in known_categories():
            intro = copy[f"submenu_{cat}"]["intro"]
            assert set(intro.keys()) == VALID_LEVELS, (
                f"Sub-menu {cat} intro missing levels: "
                f"{VALID_LEVELS - set(intro.keys())}"
            )

    def test_every_submenu_has_back_button(self):
        for cat in known_categories():
            copy = menu_formatter._load_copy()
            buttons = copy[f"submenu_{cat}"]["buttons"]
            assert buttons[-1]["callback"] == "menu:main", (
                f"Sub-menu {cat} last button must be back-to-main"
            )
            assert "Quay về" in buttons[-1]["label"]

    def test_every_submenu_has_hint(self):
        copy = menu_formatter._load_copy()
        for cat in known_categories():
            hint = copy[f"submenu_{cat}"].get("hint", "")
            assert hint.strip(), f"Sub-menu {cat} missing free-form hint"


# ============================================================
# Telegram limits + label sanity
# ============================================================


class TestTelegramLimits:
    def test_all_callbacks_under_64_bytes(self):
        for menu_key, btn in _all_buttons():
            data = btn["callback"]
            n = len(data.encode("utf-8"))
            assert n <= CALLBACK_DATA_MAX_BYTES, (
                f"{menu_key}: callback {data!r} = {n} bytes > {CALLBACK_DATA_MAX_BYTES}"
            )

    def test_button_labels_are_reasonable_length(self):
        # Mobile readability target is ≤16 chars; Vietnamese diacritics
        # + emoji push some labels to 18-20. Keep the cap at 24 — that
        # still fits one line on iPhone SE while allowing intelligible
        # Vietnamese phrases.
        MAX = 24
        for menu_key, btn in _all_buttons():
            label = btn["label"]
            assert len(label) <= MAX, (
                f"{menu_key}: label {label!r} = {len(label)} chars > {MAX}"
            )

    def test_callback_format_consistency(self):
        for menu_key, btn in _all_buttons():
            assert btn["callback"].startswith("menu:"), (
                f"{menu_key}: callback {btn['callback']!r} not under menu: prefix"
            )


# ============================================================
# Formatter output — Story S2 acceptance criteria
# ============================================================


def _user(name: str = "Hà"):
    """Mock user with the same get_greeting_name() shape as the real
    SQLAlchemy User model — the formatter only needs this one method.
    """
    safe_name = (name or "").strip()
    return SimpleNamespace(
        display_name=name,
        id="user-1",
        get_greeting_name=lambda: safe_name if safe_name else "bạn",
    )


class TestFormatMainMenu:
    def test_returns_text_and_keyboard(self):
        text, keyboard = format_main_menu(_user())
        assert isinstance(text, str) and text
        assert "inline_keyboard" in keyboard

    def test_includes_user_name(self):
        text, _ = format_main_menu(_user("Minh"))
        assert "Minh" in text

    def test_falls_back_to_default_when_user_has_no_name(self):
        text, _ = format_main_menu(_user(name=""))
        assert "{name}" not in text  # placeholder substituted
        assert "bạn" in text  # fallback applied

    def test_handles_none_user_gracefully(self):
        # Edge case from worker: telegram_id missing → user is None.
        text, _ = format_main_menu(None)
        assert "{name}" not in text
        assert "bạn" in text

    def test_keyboard_layout_is_2_column_grid(self):
        _, kb = format_main_menu(_user())
        rows = kb["inline_keyboard"]
        # 5 buttons, 2 per row → 3 rows (last has 1).
        assert len(rows) == 3
        assert len(rows[0]) == 2
        assert len(rows[-1]) == 1

    def test_unknown_level_falls_back_to_default(self):
        text, _ = format_main_menu(_user(), level="alien-level")
        # Should match what young_prof intro produces — the default.
        default_text, _ = format_main_menu(_user(), level=DEFAULT_LEVEL)
        assert text == default_text


class TestFormatSubmenu:
    @pytest.mark.parametrize("cat", ["assets", "expenses", "cashflow", "goals", "market"])
    def test_submenu_has_back_button_last(self, cat):
        _, kb = format_submenu(_user(), cat)
        rows = kb["inline_keyboard"]
        last_btn = rows[-1][0]
        assert last_btn["callback_data"] == "menu:main"
        assert "Quay về" in last_btn["text"]

    @pytest.mark.parametrize("cat", ["assets", "expenses", "cashflow", "goals", "market"])
    def test_submenu_layout_is_one_per_row(self, cat):
        _, kb = format_submenu(_user(), cat)
        for row in kb["inline_keyboard"]:
            assert len(row) == 1, f"{cat}: expected single-column layout"

    def test_unknown_category_raises_value_error(self):
        with pytest.raises(ValueError):
            format_submenu(_user(), "nonexistent")

    def test_assets_submenu_includes_title_and_intro(self):
        text, _ = format_submenu(_user("Phương"), "assets")
        assert "TÀI SẢN" in text
        assert "Phương" in text


class TestBackKeyboard:
    def test_back_keyboard_has_one_button_to_main(self):
        kb = back_to_main_keyboard()
        rows = kb["inline_keyboard"]
        assert len(rows) == 1 and len(rows[0]) == 1
        assert rows[0][0]["callback_data"] == "menu:main"


# ============================================================
# Callback router — Story S4 acceptance criteria
# ============================================================


class TestHandleMenuCallback:
    @pytest.mark.asyncio
    async def test_returns_false_for_non_menu_prefix(self):
        from backend.bot.handlers.menu_handler import handle_menu_callback

        result = await handle_menu_callback(
            db=None,
            callback_query={"data": "intent_confirm:yes", "id": "x"},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_legacy_menu_prefix(self):
        # ``menu:ocr`` belongs to the V1 flat menu — Epic 1 must defer
        # to the legacy handler (returns False) so the cutover stays safe.
        from backend.bot.handlers.menu_handler import handle_menu_callback

        result = await handle_menu_callback(
            db=None,
            callback_query={"data": "menu:ocr", "id": "x"},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_data_missing(self):
        from backend.bot.handlers.menu_handler import handle_menu_callback

        # Empty data string is treated as "not for me".
        assert (
            await handle_menu_callback(db=None, callback_query={"id": "x"})
            is False
        )
        assert (
            await handle_menu_callback(
                db=None, callback_query={"data": "", "id": "x"}
            )
            is False
        )


# ============================================================
# Wealth-level adaptive intros — Story S7 (Epic 2)
# ============================================================


# Wealth-tier mock users — the four bands the menu adapts to.
def _starter_user(name: str = "Minh"):
    """Net worth 17tr → wealth_level='starter'."""
    return SimpleNamespace(
        display_name=name,
        id="user-starter",
        wealth_level="starter",
        get_greeting_name=lambda: name,
    )


def _young_prof_user(name: str = "Hà"):
    """Net worth 140tr → wealth_level='young_prof'."""
    return SimpleNamespace(
        display_name=name,
        id="user-yp",
        wealth_level="young_prof",
        get_greeting_name=lambda: name,
    )


def _mass_affluent_user(name: str = "Phương"):
    """Net worth 4.5 tỷ → wealth_level='mass_affluent'."""
    return SimpleNamespace(
        display_name=name,
        id="user-ma",
        wealth_level="mass_affluent",
        get_greeting_name=lambda: name,
    )


def _hnw_user(name: str = "Tùng"):
    """Net worth 13 tỷ → wealth_level='hnw'."""
    return SimpleNamespace(
        display_name=name,
        id="user-hnw",
        wealth_level="hnw",
        get_greeting_name=lambda: name,
    )


class TestAdaptiveIntros:
    """Same buttons across wealth levels, distinct intro copy.

    Mirrors the manual screenshot matrix in the issue (4 personas × 5
    sub-menus). Tests assert on **structural** properties (rendering
    matches the YAML, levels differ from each other, buttons match)
    rather than specific Vietnamese phrases — copy tweaks shouldn't
    flake the test, only behaviour changes should.
    """

    @pytest.mark.parametrize(
        "user_factory,level",
        [
            (_starter_user, "starter"),
            (_young_prof_user, "young_prof"),
            (_mass_affluent_user, "mass_affluent"),
            (_hnw_user, "hnw"),
        ],
    )
    def test_main_menu_renders_yaml_for_each_level(self, user_factory, level):
        from backend.bot.formatters.menu_formatter import _load_copy

        user = user_factory()
        text, _ = format_main_menu(user, level=level)

        # The level's YAML title + intro must appear verbatim (after
        # the {name} placeholder is substituted) in the rendered text.
        copy = _load_copy()["main_menu"]
        expected_title = copy["title"][level].format(name=user.display_name)
        expected_intro = copy["intro"][level].format(name=user.display_name)
        assert expected_title in text
        assert expected_intro in text

    def test_each_level_produces_distinct_main_menu_text(self):
        # All 4 levels must render different text — otherwise the
        # adaptive layer is a no-op. Compare pairwise (6 pairs).
        levels = ["starter", "young_prof", "mass_affluent", "hnw"]
        renders = {
            lvl: format_main_menu(_user(), level=lvl)[0] for lvl in levels
        }
        for i, a in enumerate(levels):
            for b in levels[i + 1:]:
                assert renders[a] != renders[b], (
                    f"Levels {a} and {b} render identical main menu text"
                )

    @pytest.mark.parametrize(
        "category", ["assets", "expenses", "cashflow", "goals", "market"]
    )
    def test_each_level_produces_distinct_submenu_text(self, category):
        levels = ["starter", "young_prof", "mass_affluent", "hnw"]
        renders = {
            lvl: format_submenu(_user(), category, level=lvl)[0]
            for lvl in levels
        }
        for i, a in enumerate(levels):
            for b in levels[i + 1:]:
                assert renders[a] != renders[b], (
                    f"{category}: levels {a} and {b} render identically"
                )

    def test_buttons_identical_across_levels(self):
        levels = ["starter", "young_prof", "mass_affluent", "hnw"]
        keyboards = [
            format_main_menu(_user(), level=lvl)[1]["inline_keyboard"]
            for lvl in levels
        ]
        button_lists = [
            [(btn["text"], btn["callback_data"]) for row in kb for btn in row]
            for kb in keyboards
        ]
        for other in button_lists[1:]:
            assert other == button_lists[0]

    def test_invalid_level_falls_back_to_default(self):
        # Defensive: future migration adding a new band shouldn't crash
        # users whose wealth_level column hasn't been recomputed.
        text, _ = format_main_menu(_user(), level="legendary")
        default_text, _ = format_main_menu(_user(), level=None)
        assert text == default_text


# ============================================================
# Coexistence — Story S9
# ============================================================


class TestMenuCoexistence:
    """Menu and free-form queries must not interfere.

    Phase 3.5 routes text via ``handle_text_message``; Phase 3.6 routes
    callbacks via ``handle_menu_callback``. They share no state. These
    tests pin the boundary so a future refactor can't accidentally
    couple them.
    """

    @pytest.mark.asyncio
    async def test_legacy_menu_callback_does_not_raise(self):
        """Stale V1 callbacks (deployed before the cutover) must
        return False quietly so the legacy handler in the worker can
        respond. Anything else risks a stuck spinner for users whose
        chat history still has old menu bubbles.
        """
        from backend.bot.handlers.menu_handler import handle_menu_callback

        for legacy in ("menu:gmail_scan", "menu:add_expense", "menu:advice"):
            assert (
                await handle_menu_callback(
                    db=None, callback_query={"data": legacy, "id": "x"}
                )
                is False
            )

    @pytest.mark.asyncio
    async def test_unknown_top_level_returns_false(self):
        # Future V3 menus might use ``menu:dashboard`` etc. — until then,
        # the new handler stays out of their way.
        from backend.bot.handlers.menu_handler import handle_menu_callback

        assert (
            await handle_menu_callback(
                db=None, callback_query={"data": "menu:future", "id": "x"}
            )
            is False
        )


# ============================================================
# /dashboard command — Story S8
# ============================================================


class TestCmdDashboard:
    @pytest.mark.asyncio
    async def test_sends_placeholder_when_miniapp_url_unset(self, monkeypatch):
        from backend.bot.handlers import menu_handler

        sent = {}

        async def fake_send_message(**kwargs):
            sent.update(kwargs)

        monkeypatch.setattr(menu_handler, "send_message", fake_send_message)

        # Force unset miniapp_base_url — emulates first-deploy / dev.
        from backend.config import get_settings

        settings = get_settings()
        original = settings.miniapp_base_url
        settings.miniapp_base_url = ""
        try:
            await menu_handler.cmd_dashboard(db=None, chat_id=42, user=None)
        finally:
            settings.miniapp_base_url = original

        # Assert against the exported constant — copy tweaks shouldn't
        # break the test, only behaviour changes should.
        assert sent["text"] == menu_handler.DASHBOARD_NOT_CONFIGURED_TEXT
        assert sent["chat_id"] == 42
        # No keyboard rendered — placeholder is the whole message.
        assert "reply_markup" not in sent

    @pytest.mark.asyncio
    async def test_sends_web_app_button_when_url_configured(self, monkeypatch):
        from backend.bot.handlers import menu_handler

        sent = {}

        async def fake_send_message(**kwargs):
            sent.update(kwargs)

        monkeypatch.setattr(menu_handler, "send_message", fake_send_message)

        from backend.config import get_settings

        settings = get_settings()
        original = settings.miniapp_base_url
        settings.miniapp_base_url = "https://example.com"
        try:
            await menu_handler.cmd_dashboard(db=None, chat_id=42, user=None)
        finally:
            settings.miniapp_base_url = original

        keyboard = sent["reply_markup"]["inline_keyboard"]
        url = keyboard[0][0]["web_app"]["url"]
        # Pin the path + the analytics-attribution query param so the
        # briefing funnel and the /dashboard funnel stay distinguishable.
        assert url == "https://example.com/miniapp/wealth?source=dashboard_command"


# ============================================================
# Cross-check: every submenu action has a wired handler or fallback
# ============================================================


class TestActionCoverage:
    """Every action button in the YAML must have either a direct handler,
    an intent mapping, or an advisory mapping. Otherwise the user lands
    on the coming-soon stub — which is fine but worth flagging.
    """

    def test_all_actions_have_some_wiring(self):
        from backend.bot.handlers.menu_handler import (
            _ADVISORY_MAP,
            _DIRECT_HANDLERS,
            _INTENT_MAP,
        )

        wired = set(_DIRECT_HANDLERS) | set(_INTENT_MAP) | set(_ADVISORY_MAP)
        copy = menu_formatter._load_copy()

        coming_soon: list[tuple[str, str]] = []
        for cat in known_categories():
            for btn in copy[f"submenu_{cat}"]["buttons"]:
                cb = btn["callback"]
                parts = cb.split(":")
                if len(parts) != 3:
                    continue  # skip nav buttons like menu:main
                key = (parts[1], parts[2])
                if key not in wired:
                    coming_soon.append(key)

        # Epic 1 explicitly accepts coming-soon for capabilities not yet
        # built (per phase-3.6-issues.md S6). We only fail the test if
        # a *recognised* action key is unwired without that intent.
        # The current Epic 1 wiring covers all 22 actions.
        assert coming_soon == [], (
            f"Unwired actions (coming-soon stub will fire): {coming_soon}"
        )
