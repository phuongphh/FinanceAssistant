"""Telegram custom-emoji rendering helpers.

The helper keeps the plain static emoji in ``text`` and adds Bot API
``custom_emoji`` entities over mapped emoji spans. Telegram Premium clients can
animate the custom emoji; all other clients still see the original Unicode
emoji, so this path is safe to use in high-frequency notifications.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, TypedDict

import yaml

_EMOJI_MAP_PATH = Path(__file__).resolve().parents[3] / "content" / "emoji_animation_map.yaml"


class MessageEntity(TypedDict, total=False):
    type: str
    offset: int
    length: int
    custom_emoji_id: str


EmojiMapping = Mapping[str, Mapping[str, Any]]


@lru_cache(maxsize=1)
def load_emoji_animation_map() -> dict[str, dict[str, Any]]:
    """Load and cache the custom emoji map from content YAML."""
    with open(_EMOJI_MAP_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def mapping_for_context(context: str | None = None) -> dict[str, dict[str, Any]]:
    """Return mappings allowed for ``context``.

    ``None`` returns the full map. Context filtering keeps low-impact bot copy
    static while allowing Epic 5 touchpoints to opt in deliberately.
    """
    mapping = load_emoji_animation_map()
    if not context:
        return mapping
    return {
        key: value
        for key, value in mapping.items()
        if context in set(value.get("contexts") or [])
    }


def _utf16_len(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _iter_entries(mapping: EmojiMapping) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for item in mapping.values():
        static = item.get("static")
        animation_id = item.get("animation_id")
        if isinstance(static, str) and static and isinstance(animation_id, str) and animation_id:
            entries.append((static, animation_id))
    # Prefer longer emoji sequences first (e.g. ⚠️ before ⚠) to avoid partial
    # matches when variation selectors are present.
    return sorted(entries, key=lambda pair: len(pair[0]), reverse=True)


def render_with_animation(
    text: str,
    mapping: EmojiMapping | None = None,
) -> tuple[str, list[MessageEntity]]:
    """Return ``text`` plus Telegram custom-emoji entities for mapped emoji.

    Unknown emoji are left untouched without entities. Offsets and lengths use
    Telegram's required UTF-16 code-unit indexing, not Python code-point indexes.
    """
    if not text:
        return text, []

    active_mapping = mapping if mapping is not None else load_emoji_animation_map()
    entries = _iter_entries(active_mapping)
    if not entries:
        return text, []

    entities: list[MessageEntity] = []
    index = 0
    utf16_offset = 0
    text_len = len(text)

    while index < text_len:
        matched: tuple[str, str] | None = None
        for static, animation_id in entries:
            if text.startswith(static, index):
                matched = (static, animation_id)
                break

        if matched is None:
            utf16_offset += _utf16_len(text[index])
            index += 1
            continue

        static, animation_id = matched
        length = _utf16_len(static)
        entities.append(
            {
                "type": "custom_emoji",
                "offset": utf16_offset,
                "length": length,
                "custom_emoji_id": animation_id,
            }
        )
        index += len(static)
        utf16_offset += length

    return text, entities


def render_context(
    text: str,
    context: str,
) -> tuple[str, list[MessageEntity]]:
    """Render ``text`` using only mappings tagged for ``context``."""
    return render_with_animation(text, mapping_for_context(context))


def message_kwargs_for_animation(text: str, context: str) -> dict[str, Any]:
    """Small adapter helper for Telegram send/edit calls.

    Returns an empty dict when no mapped emoji are present, avoiding extra Bot
    API payload size on ordinary messages.
    """
    _, entities = render_context(text, context)
    return {"entities": entities} if entities else {}


__all__ = [
    "MessageEntity",
    "load_emoji_animation_map",
    "mapping_for_context",
    "message_kwargs_for_animation",
    "render_context",
    "render_with_animation",
]
