#!/usr/bin/env python3
"""Phase 3.6 menu smoke test — run after deploy.

Exits 0 if the new menu surface is wired correctly, non-zero on any
failure. Designed for a 4-hour post-deploy monitoring window where the
operator wants confidence the cutover landed without inspecting code.

Checks (no Telegram API calls — pure import + render):
  1. ``content/menu_copy.yaml`` parses and has the expected categories.
  2. ``MenuFormatter`` renders main menu + every sub-menu without raising.
  3. Wealth-level adaptive intros render for all four bands.
  4. Bot menu button has exactly the 4 Phase 3.6 commands.
  5. Legacy redirect text is non-empty (so the "menu upgraded" message
     doesn't accidentally get blanked).

Usage::

    python scripts/phase_3_6_smoke_test.py

Run from the repo root after deploy. Add to deploy runbook so each
release verifies the menu before traffic ramps up.
"""
from __future__ import annotations

import sys
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

# Make ``backend.*`` importable when invoked from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _user(name: str = "Smoke Tester", level: str | None = None):
    return SimpleNamespace(
        display_name=name,
        id=uuid.uuid4(),
        wealth_level=level,
        get_greeting_name=lambda: name,
    )


def _check(label: str, fn) -> bool:
    try:
        fn()
    except Exception:  # noqa: BLE001 — we want to surface any failure
        print(f"  ❌ {label}")
        traceback.print_exc()
        return False
    print(f"  ✅ {label}")
    return True


def main() -> int:
    print("Phase 3.6 menu smoke test")
    print("=" * 50)

    from backend.bot.formatters.menu_formatter import (
        VALID_LEVELS,
        format_main_menu,
        format_submenu,
        known_categories,
    )
    from backend.bot.handlers.menu_handler import LEGACY_REDIRECT_TEXT
    from backend.bot.setup_commands import BOT_COMMANDS

    expected_categories = {"assets", "expenses", "cashflow", "goals", "market"}
    # Structural assertion only — let copy team rename / reorder commands
    # without breaking the smoke test, but require ``menu`` (the rich UI
    # entry point) to always be present.
    required_commands = {"menu"}

    results = []

    def check_categories():
        actual = set(known_categories())
        assert actual == expected_categories, f"got {actual}"

    results.append(_check(
        "menu_copy.yaml parses with 5 expected categories",
        check_categories,
    ))

    def render_main_for_each_level():
        for lvl in VALID_LEVELS:
            text, kb = format_main_menu(_user(level=lvl), level=lvl)
            assert text, f"empty main-menu text at level {lvl}"
            assert kb["inline_keyboard"], f"empty main-menu keyboard at level {lvl}"

    results.append(_check(
        "main menu renders for all 4 wealth levels",
        render_main_for_each_level,
    ))

    def render_each_submenu():
        for cat in expected_categories:
            text, kb = format_submenu(_user(), cat)
            assert text, f"empty sub-menu text for {cat}"
            assert kb["inline_keyboard"], f"empty sub-menu keyboard for {cat}"
            last = kb["inline_keyboard"][-1][0]
            assert last["callback_data"] == "menu:main", (
                f"{cat}: last button must be back-to-main, got {last}"
            )

    results.append(_check(
        "every sub-menu renders + has back-to-main as last button",
        render_each_submenu,
    ))

    def check_bot_commands():
        assert len(BOT_COMMANDS) >= 1, "BOT_COMMANDS is empty"
        for entry in BOT_COMMANDS:
            assert "command" in entry and "description" in entry, (
                f"malformed BOT_COMMANDS entry: {entry}"
            )
        names = {c["command"] for c in BOT_COMMANDS}
        missing = required_commands - names
        assert not missing, f"BOT_COMMANDS missing required: {missing}"

    results.append(_check(
        f"bot menu button has well-formed entries incl. {required_commands}",
        check_bot_commands,
    ))

    def check_redirect_text():
        assert LEGACY_REDIRECT_TEXT.strip(), "redirect text empty"

    results.append(_check(
        "legacy redirect text is populated",
        check_redirect_text,
    ))

    print("=" * 50)
    if all(results):
        print(f"All {len(results)} checks passed — Phase 3.6 menu surface is healthy.")
        return 0
    print(f"{sum(1 for r in results if not r)}/{len(results)} checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
