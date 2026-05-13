"""Inline keyboard for storytelling confirmation (P3A-19).

Three-button confirmation surfaced after the LLM extracts transactions:

    story:confirm:all      — save every pending transaction as-is
    story:confirm:edit     — enter per-item edit mode (P3A-19 stretch)
    story:confirm:cancel   — discard everything, drop mode

Callback prefix ``story:`` mirrors ``briefing:`` / ``asset_add:`` so
the worker's callback router can dispatch by prefix.
"""
from __future__ import annotations

from backend.bot.keyboards.common import build_callback

CB_STORY = "story"

STORY_ACTION_CONFIRM_ALL = "all"
STORY_ACTION_EDIT = "edit"
STORY_ACTION_CANCEL = "cancel"


def storytelling_confirmation_keyboard() -> dict:
    """3-button keyboard: [✅ Đúng hết] [✏️ Sửa] / [❌ Bỏ hết]."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Đúng hết",
                    "callback_data": build_callback(
                        CB_STORY, "confirm", STORY_ACTION_CONFIRM_ALL
                    ),
                },
                {
                    "text": "✏️ Sửa",
                    "callback_data": build_callback(
                        CB_STORY, "confirm", STORY_ACTION_EDIT
                    ),
                },
            ],
            [
                {
                    "text": "❌ Bỏ hết",
                    "callback_data": build_callback(
                        CB_STORY, "confirm", STORY_ACTION_CANCEL
                    ),
                },
            ],
        ]
    }
