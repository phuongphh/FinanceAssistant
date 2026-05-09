"""Inline keyboards for the recurring-pattern wizard + reminders.

Two callback prefixes (separate so worker dispatch is unambiguous):

    recurring:start                       — open add wizard
    recurring:list                        — refresh list view
    recurring:category:<code>             — pick category
    recurring:reminders:<on|off>          — toggle reminders during add
    recurring:manage                     — choose a pattern to manage
    recurring:select:<pattern_uuid>       — show edit/reminder/delete actions
    recurring:edit:<pattern_uuid>         — edit-amount sub-wizard
    recurring:reminder_on:<pattern_uuid>  — enable reminders
    recurring:disable:<pattern_uuid>      — confirm pause
    recurring:disable_confirm:<uuid>      — actually pause
    recurring:cancel                      — abort

    reminder:paid:<pattern_uuid>          — reminder action: paid
    reminder:delay:<pattern_uuid>         — reminder action: snooze 2d
    reminder:disable:<pattern_uuid>       — reminder action: disable
    reminder:paid_all                     — bundled "đã trả tất cả"
                                            (target ids in message text)
"""
from __future__ import annotations

import uuid

from backend.bot.keyboards.common import build_callback
from backend.config.categories import get_all_categories

InlineKeyboardMarkup = dict

CB_RECURRING = "recurring"
CB_REMINDER = "reminder"


def recurring_category_keyboard() -> InlineKeyboardMarkup:
    """13 categories from ``backend.config.categories`` in 2-col grid."""
    cats = get_all_categories()
    rows: list[list[dict]] = []
    for i in range(0, len(cats), 2):
        chunk = cats[i:i + 2]
        rows.append([
            {
                "text": f"{c.emoji} {c.name_vi}",
                "callback_data": build_callback(CB_RECURRING, "category", c.code),
            }
            for c in chunk
        ])
    rows.append([
        {"text": "❌ Hủy", "callback_data": build_callback(CB_RECURRING, "cancel")},
    ])
    return {"inline_keyboard": rows}


def recurring_reminders_toggle_keyboard() -> InlineKeyboardMarkup:
    """Last step of the wizard — bật/tắt nhắc nhở."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔔 Bật nhắc",
                    "callback_data": build_callback(CB_RECURRING, "reminders", "on"),
                },
                {
                    "text": "🔕 Không nhắc",
                    "callback_data": build_callback(CB_RECURRING, "reminders", "off"),
                },
            ],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_RECURRING, "cancel")}],
        ]
    }


def recurring_list_actions_keyboard(
    pattern_id: uuid.UUID | str,
    *,
    enable_reminders: bool,
) -> InlineKeyboardMarkup:
    """Action buttons shown only after the user selects one pattern
    from the manage list.

    Keeping edit/remind/delete off the read-only overview prevents
    accidental destructive taps while still giving a fast two-step
    management path.
    """
    pid = str(pattern_id)
    bell_btn = (
        {
            "text": "🔕 Tắt nhắc",
            "callback_data": build_callback(CB_REMINDER, "disable", pid),
        }
        if enable_reminders
        else {
            "text": "🔔 Bật nhắc",
            "callback_data": build_callback(CB_RECURRING, "reminder_on", pid),
        }
    )
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✏️ Sửa số tiền",
                    "callback_data": build_callback(CB_RECURRING, "edit", pid),
                },
                bell_btn,
            ],
            [{
                "text": "🗑️ Xóa",
                "callback_data": build_callback(CB_RECURRING, "disable", pid),
            }],
            [{
                "text": "◀️ Chọn khoản khác",
                "callback_data": build_callback(CB_RECURRING, "manage"),
            }],
        ]
    }


def recurring_disable_confirm_keyboard(
    pattern_id: uuid.UUID | str,
) -> InlineKeyboardMarkup:
    """Two-tap delete — patterns take 4-5 taps to add, accidental
    deletes from the list shouldn't lose them."""
    pid = str(pattern_id)
    return {
        "inline_keyboard": [
            [{
                "text": "🗑️ Xóa thật",
                "callback_data": build_callback(CB_RECURRING, "disable_confirm", pid),
            }],
            [{
                "text": "❌ Không, giữ lại",
                "callback_data": build_callback(CB_RECURRING, "list"),
            }],
        ]
    }


def recurring_list_footer_keyboard() -> InlineKeyboardMarkup:
    """Read-only overview footer: add, enter manage mode, or go back to
    the Expenses submenu.
    """
    return {
        "inline_keyboard": [
            [{
                "text": "➕ Thêm khoản định kỳ",
                "callback_data": build_callback(CB_RECURRING, "start"),
            }],
            [{
                "text": "✏️ Sửa khoản định kỳ",
                "callback_data": build_callback(CB_RECURRING, "manage"),
            }],
            [{"text": "◀️ Quay về Chi tiêu", "callback_data": "menu:expenses"}],
        ]
    }


def recurring_manage_list_keyboard(
    patterns: list,
) -> InlineKeyboardMarkup:
    """Pattern picker for the edit/reminder/delete flow."""
    rows: list[list[dict]] = []
    for p in patterns:
        status = "⏸️ " if not getattr(p, "is_active", True) else ""
        rows.append([{
            "text": f"{status}{p.name}",
            "callback_data": build_callback(CB_RECURRING, "select", str(p.id)),
        }])
    rows.append([{
        "text": "◀️ Quay lại danh sách",
        "callback_data": build_callback(CB_RECURRING, "list"),
    }])
    return {"inline_keyboard": rows}


# ---------------------------------------------------------------------
# Reminder keyboards (S9 + S10)
# ---------------------------------------------------------------------


def reminder_action_keyboard(pattern_id: uuid.UUID | str) -> InlineKeyboardMarkup:
    """Three-button keyboard attached to every single-pattern reminder.

    Layout: paid + delay on row 1 (most-tapped pair); disable on
    row 2 (separated so a finger slip doesn't accidentally silence
    a stream)."""
    pid = str(pattern_id)
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Đã trả",
                    "callback_data": build_callback(CB_REMINDER, "paid", pid),
                },
                {
                    "text": "⏭️ Trễ vài ngày",
                    "callback_data": build_callback(CB_REMINDER, "delay", pid),
                },
            ],
            [{
                "text": "🔕 Tắt nhắc nhở",
                "callback_data": build_callback(CB_REMINDER, "disable", pid),
            }],
        ]
    }


def reminder_bundle_keyboard(
    pattern_ids: list[uuid.UUID | str],
) -> InlineKeyboardMarkup:
    """Bundled-reminder keyboard. ``Đã trả tất cả`` records each
    pattern as paid; ``Ghi chi tiết`` opens per-pattern wizard
    flow (handled in handler).

    The pattern ids are NOT embedded in the callback (would blow
    past Telegram's 64-byte cap). The handler reads them from the
    bundle's message text fingerprint stored in user wizard state."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Đã trả tất cả",
                    "callback_data": build_callback(CB_REMINDER, "paid_all"),
                },
                {
                    "text": "📝 Ghi chi tiết",
                    "callback_data": build_callback(CB_REMINDER, "detail"),
                },
            ],
            [{
                "text": "🔕 Tắt nhắc tất cả",
                "callback_data": build_callback(CB_REMINDER, "disable_all"),
            }],
        ]
    }


# ---------------------------------------------------------------------
# Suggestion keyboard (S8)
# ---------------------------------------------------------------------


def suggestion_keyboard(suggestion_id: int) -> InlineKeyboardMarkup:
    """Keyboard for an auto-detected suggestion. Outcomes are recorded
    against ``pattern_suggestions_log.id`` so we can de-spam future
    detections."""
    sid = str(suggestion_id)
    return {
        "inline_keyboard": [
            [{
                "text": "✅ Đúng, ghi nhận",
                "callback_data": build_callback(CB_RECURRING, "accept", sid),
            }],
            [{
                "text": "✏️ Sửa lại",
                "callback_data": build_callback(CB_RECURRING, "edit_suggest", sid),
            }],
            [{
                "text": "❌ Không, bỏ qua",
                "callback_data": build_callback(CB_RECURRING, "reject", sid),
            }],
        ]
    }
