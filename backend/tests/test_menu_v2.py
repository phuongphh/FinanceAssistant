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
