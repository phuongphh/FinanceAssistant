"""Smoke tests for the briefing inline keyboard.

Two invariants worth pinning:

- Every callback_data stays under Telegram's 64-byte cap (a typo in
  ``build_callback`` would only surface in production otherwise).
- The action constants used by the keyboard match the ones the
  handler dispatches on — divergence here means buttons get registered
  but never fire their analytics event.
"""
from __future__ import annotations

from backend.bot.handlers import briefing as briefing_handler
from backend.bot.keyboards.briefing_keyboard import (
    BRIEFING_ACTION_ADD_ASSET,
    BRIEFING_ACTION_DASHBOARD,
    BRIEFING_ACTION_SETTINGS,
    BRIEFING_ACTION_STORY,
    CB_BRIEFING,
    briefing_actions_keyboard,
)
from backend.bot.keyboards.common import (
    TELEGRAM_CALLBACK_DATA_MAX_BYTES,
    parse_callback,
)


def test_keyboard_layout_2x2():
    kb = briefing_actions_keyboard()
    rows = kb["inline_keyboard"]
    assert len(rows) == 2
    for row in rows:
        assert len(row) == 2


def test_every_callback_under_limit():
    kb = briefing_actions_keyboard()
    for row in kb["inline_keyboard"]:
        for btn in row:
            data = btn["callback_data"]
            assert len(data.encode("utf-8")) <= TELEGRAM_CALLBACK_DATA_MAX_BYTES


def test_briefing_callbacks_use_canonical_prefix():
    kb = briefing_actions_keyboard()
    seen_actions = set()
    for row in kb["inline_keyboard"]:
        for btn in row:
            prefix, parts = parse_callback(btn["callback_data"])
            if prefix == CB_BRIEFING:
                seen_actions.add(parts[0])

    # Every action the keyboard surfaces must be one the handler knows
    # how to dispatch — keeps keyboard ↔ handler in lockstep.
    assert BRIEFING_ACTION_DASHBOARD in seen_actions
    assert BRIEFING_ACTION_STORY in seen_actions
    assert BRIEFING_ACTION_ADD_ASSET in seen_actions
    assert BRIEFING_ACTION_SETTINGS in seen_actions
    for action in seen_actions:
        assert action in briefing_handler._ACTION_TO_EVENT
