"""Inline keyboards for the /life_events wizard (Phase 4B Epic 2).

All callbacks share the ``life_event:`` prefix so the worker can route the
whole namespace to ``backend.bot.handlers.life_event_entry``. Telegram
callback data is limited to 64 bytes UTF-8 — see ``build_callback`` in
``backend/bot/keyboards/common.py``.
"""
from __future__ import annotations

import uuid
from typing import Sequence

from backend.bot.keyboards.common import build_callback
from backend.life_events.presets import PRESET_ORDER
from backend.models.life_event import LifeEventType


CB_LIFE_EVENT = "life_event"


def life_events_menu_keyboard() -> dict:
    """Top-level menu shown by /life_events command."""
    return {
        "inline_keyboard": [
            [{"text": "📋 Xem danh sách", "callback_data": build_callback(CB_LIFE_EVENT, "list")}],
            [{"text": "➕ Thêm mốc", "callback_data": build_callback(CB_LIFE_EVENT, "add")}],
            [{"text": "🗑 Xóa mốc", "callback_data": build_callback(CB_LIFE_EVENT, "delete_menu")}],
            [{"text": "◀️ Quay về Twin", "callback_data": "menu:twin"}],
        ]
    }


def event_type_picker_keyboard(type_labels: dict[LifeEventType, dict]) -> dict:
    """Show 6 buttons (one per LifeEventType) using copy from content/life_events.yaml.

    ``type_labels`` maps each LifeEventType to its ``{"icon", "short_label"}`` dict.
    """
    rows = []
    # 2 columns × 3 rows for the first 6 types — easier to scan than 6 single rows.
    pair: list[dict] = []
    for event_type in PRESET_ORDER:
        meta = type_labels.get(event_type, {})
        text = f"{meta.get('icon', '')} {meta.get('short_label', event_type.value)}".strip()
        pair.append(
            {
                "text": text,
                "callback_data": build_callback(CB_LIFE_EVENT, "pick_type", event_type.value),
            }
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([
        {"text": "❌ Hủy", "callback_data": build_callback(CB_LIFE_EVENT, "cancel")},
    ])
    return {"inline_keyboard": rows}


def review_preset_keyboard() -> dict:
    """Shown after the user picks a preset type — accept or customize."""
    return {
        "inline_keyboard": [
            [{"text": "✅ Dùng ước tính này", "callback_data": build_callback(CB_LIFE_EVENT, "use_preset")}],
            [{"text": "✏️ Tùy chỉnh chi tiết", "callback_data": build_callback(CB_LIFE_EVENT, "customize")}],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_LIFE_EVENT, "cancel")}],
        ]
    }


def confirm_save_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✅ Xác nhận", "callback_data": build_callback(CB_LIFE_EVENT, "confirm")}],
            [{"text": "✏️ Sửa lại", "callback_data": build_callback(CB_LIFE_EVENT, "restart")}],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_LIFE_EVENT, "cancel")}],
        ]
    }


def delete_pick_keyboard(events: Sequence) -> dict:
    """Show a button per active event so the user can pick which to delete."""
    rows = []
    for event in events:
        title = event.title or event.event_type
        label = f"🗑 {title[:40]}"
        rows.append(
            [{"text": label, "callback_data": build_callback(CB_LIFE_EVENT, "delete_pick", str(event.id))}]
        )
    rows.append(
        [{"text": "◀️ Quay về", "callback_data": build_callback(CB_LIFE_EVENT, "menu")}]
    )
    return {"inline_keyboard": rows}


def delete_confirm_keyboard(event_id: uuid.UUID) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Xóa", "callback_data": build_callback(CB_LIFE_EVENT, "delete_confirm", str(event_id))},
                {"text": "❌ Giữ lại", "callback_data": build_callback(CB_LIFE_EVENT, "delete_menu")},
            ]
        ]
    }


def back_to_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "◀️ Quay về", "callback_data": build_callback(CB_LIFE_EVENT, "menu")}],
        ]
    }
