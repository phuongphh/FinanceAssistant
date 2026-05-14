"""Phase 3.6 menu formatter — text + Telegram inline keyboard dicts.

Pure formatter with no DB / network IO. The wealth-level lookup is
caller input rather than computed here so this module stays trivially
testable. Epic 1 callers default to ``WealthLevel.YOUNG_PROFESSIONAL``;
Epic 2 wires real detection at the call site.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.wealth.ladder import WealthLevel

logger = logging.getLogger(__name__)

DEFAULT_LEVEL = WealthLevel.YOUNG_PROFESSIONAL.value
VALID_LEVELS = frozenset(level.value for level in WealthLevel)


def _pick_localized(
    bucket: dict[str, str], band: str, *, context: str
) -> str:
    """Return ``bucket[band]`` with a graceful fallback path.

    Order: requested ``band`` → ``DEFAULT_LEVEL`` → first available key.
    Missing keys are logged once so content drift is visible without
    breaking the webhook (root cause of issue #635).
    """
    if band in bucket:
        return bucket[band]
    logger.warning(
        "menu_copy missing localization for %s at level %r — falling back",
        context,
        band,
    )
    if DEFAULT_LEVEL in bucket:
        return bucket[DEFAULT_LEVEL]
    # Last resort: any value we have. ``known_categories`` and the
    # YAML schema test guarantee at least one key exists in practice.
    return next(iter(bucket.values()))

_MENU_COPY_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "menu_copy.yaml"
)


@lru_cache(maxsize=1)
def _load_copy() -> dict[str, Any]:
    """Load and cache menu_copy.yaml. File edits in production require
    a process restart — same constraint as every other content YAML.
    """
    with open(_MENU_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_level(level: str | None) -> str:
    if level and level in VALID_LEVELS:
        return level
    return DEFAULT_LEVEL


def _name_for(user) -> str:
    if user is None:
        return "bạn"
    return user.get_greeting_name()


def format_main_menu(
    user, *, level: str | None = None
) -> tuple[str, dict]:
    """Build the main menu (Level 1) text + inline keyboard.

    Layout: 5 buttons in a 2-column grid (3 rows; last row has 1 button).
    """
    config = _load_copy()["main_menu"]
    band = _resolve_level(level)
    name = _name_for(user)

    title = _pick_localized(config["title"], band, context="main_menu.title").format(name=name)
    intro = _pick_localized(config["intro"], band, context="main_menu.intro").format(name=name)
    text = f"{title}\n\n{intro}\n\n{config['hint']}"

    buttons = config["buttons"]
    keyboard: list[list[dict]] = []
    for i in range(0, len(buttons), 2):
        row = [
            {"text": b["label"], "callback_data": b["callback"]}
            for b in buttons[i : i + 2]
        ]
        keyboard.append(row)

    return text, {"inline_keyboard": keyboard}


def format_submenu(
    user, category: str, *, level: str | None = None
) -> tuple[str, dict]:
    """Build a sub-menu (Level 2) text + inline keyboard for a category.

    ``category`` is the bare key from main-menu callbacks (``assets``,
    ``expenses``, ``cashflow``, ``goals``, ``market``). Layout is
    1-column vertical — easier vertical scan than a 2-col grid.
    """
    config_key = f"submenu_{category}"
    copy = _load_copy()
    if config_key not in copy:
        raise ValueError(f"Unknown menu category: {category!r}")

    config = copy[config_key]
    band = _resolve_level(level)
    name = _name_for(user)

    intro = _pick_localized(
        config["intro"], band, context=f"{config_key}.intro"
    ).format(name=name)
    text = f"{config['title']}\n\n{intro}\n\n{config['hint']}"

    keyboard: list[list[dict]] = [
        [{"text": b["label"], "callback_data": b["callback"]}]
        for b in config["buttons"]
    ]
    return text, {"inline_keyboard": keyboard}


def back_to_main_keyboard() -> dict:
    """Lone "◀️ Quay về" button — escape route from action result screens."""
    return {
        "inline_keyboard": [
            [{"text": "◀️ Quay về menu", "callback_data": "menu:main"}]
        ]
    }


def get_action_copy(section: str, key: str) -> str:
    """Read user-facing copy for direct menu actions from YAML."""
    value = _load_copy().get(section, {}).get(key)
    if not isinstance(value, str) or not value.strip():
        raise KeyError(f"Missing menu action copy: {section}.{key}")
    return value


def known_categories() -> list[str]:
    return [
        key.removeprefix("submenu_")
        for key in _load_copy()
        if key.startswith("submenu_")
    ]


def get_submenu_hint(category: str) -> str:
    """Return the hint text for a submenu category, or empty string if absent."""
    config_key = f"submenu_{category}"
    config = _load_copy().get(config_key, {})
    return config.get("hint", "")


__all__ = [
    "DEFAULT_LEVEL",
    "VALID_LEVELS",
    "back_to_main_keyboard",
    "format_main_menu",
    "format_submenu",
    "get_action_copy",
    "get_submenu_hint",
    "known_categories",
]
