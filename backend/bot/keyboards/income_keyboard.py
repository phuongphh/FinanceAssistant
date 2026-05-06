"""Inline keyboards for the income-stream wizard.

Callback prefix: ``income`` (separate from ``asset_add`` so the
worker's prefix dispatch is unambiguous).

Layout:

    income:start                        — open type picker
    income:type:<stream_type>           — pick a type
    income:schedule:<schedule_type>     — pick schedule
    income:month:<1-12>                 — pick month for annual schedule
    income:start_date:<today|custom>    — pick start date shortcut
    income:cancel                       — abort wizard

    income:list                         — refresh the list view
    income:edit:<stream_uuid>           — open edit (amount only) wizard
    income:delete:<stream_uuid>         — confirm delete
    income:delete_confirm:<stream_uuid> — actual delete
    income:pause:<stream_uuid>          — pause an active stream
    income:resume:<stream_uuid>         — resume a paused stream

Total bytes: ``income:delete_confirm:`` (22) + 36-char UUID = 58
bytes — under the 64-byte Telegram cap.
"""
from __future__ import annotations

import uuid

from backend.bot.keyboards.common import build_callback
from backend.wealth.income_types import (
    ScheduleType,
    all_user_facing_types,
    get_icon,
    get_label,
)

InlineKeyboardMarkup = dict

CB_INCOME = "income"


def income_type_picker_keyboard() -> InlineKeyboardMarkup:
    """Show 5 user-facing income types (rental excluded — auto-linked).

    1 button per row for vertical scan readability; the labels are
    long-ish ("Freelance / Công việc thêm") and a 2-col layout would
    truncate them on narrow phones.
    """
    rows = []
    for t in all_user_facing_types():
        rows.append([{
            "text": f"{get_icon(t)} {get_label(t)}",
            "callback_data": build_callback(CB_INCOME, "type", t),
        }])
    rows.append([{
        "text": "❌ Hủy",
        "callback_data": build_callback(CB_INCOME, "cancel"),
    }])
    return {"inline_keyboard": rows}


def income_schedule_keyboard() -> InlineKeyboardMarkup:
    """4 schedule choices. Order = most-common first (monthly is the
    overwhelming majority for both salary and rental users)."""
    return {
        "inline_keyboard": [
            [{
                "text": "📅 Hàng tháng",
                "callback_data": build_callback(CB_INCOME, "schedule", ScheduleType.MONTHLY.value),
            }],
            [{
                "text": "📆 Hàng quý",
                "callback_data": build_callback(CB_INCOME, "schedule", ScheduleType.QUARTERLY.value),
            }],
            [{
                "text": "🗓️ Hàng năm",
                "callback_data": build_callback(CB_INCOME, "schedule", ScheduleType.ANNUALLY.value),
            }],
            [{
                "text": "🎲 Bất định",
                "callback_data": build_callback(CB_INCOME, "schedule", ScheduleType.AD_HOC.value),
            }],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_INCOME, "cancel")}],
        ]
    }


def income_month_keyboard() -> InlineKeyboardMarkup:
    """12-month picker for annual streams. 4×3 grid for compactness."""
    months_vi = [
        "Tháng 1", "Tháng 2", "Tháng 3", "Tháng 4",
        "Tháng 5", "Tháng 6", "Tháng 7", "Tháng 8",
        "Tháng 9", "Tháng 10", "Tháng 11", "Tháng 12",
    ]
    rows = []
    for i in range(0, 12, 4):
        row = [
            {
                "text": months_vi[i + j],
                "callback_data": build_callback(CB_INCOME, "month", str(i + j + 1)),
            }
            for j in range(4)
        ]
        rows.append(row)
    rows.append([{
        "text": "❌ Hủy",
        "callback_data": build_callback(CB_INCOME, "cancel"),
    }])
    return {"inline_keyboard": rows}


def income_start_date_keyboard() -> InlineKeyboardMarkup:
    """Today / custom date shortcut. Most users add streams that
    started ~now; the custom path covers historical entries."""
    return {
        "inline_keyboard": [
            [{
                "text": "📅 Hôm nay",
                "callback_data": build_callback(CB_INCOME, "start_date", "today"),
            }],
            [{
                "text": "✏️ Tự nhập (YYYY-MM-DD)",
                "callback_data": build_callback(CB_INCOME, "start_date", "custom"),
            }],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_INCOME, "cancel")}],
        ]
    }


def income_list_actions_keyboard(
    stream_id: uuid.UUID | str,
    *,
    is_active: bool,
) -> InlineKeyboardMarkup:
    """Actions shown next to each stream in the list view.

    Compact 2-col layout: edit / pause-or-resume on top, delete below.
    The pause/resume button is asymmetric on label so the user can
    see at a glance which state the row is in without parsing colours.
    """
    sid = str(stream_id)
    toggle_btn = (
        {
            "text": "⏸️ Tạm dừng",
            "callback_data": build_callback(CB_INCOME, "pause", sid),
        }
        if is_active
        else {
            "text": "▶️ Bật lại",
            "callback_data": build_callback(CB_INCOME, "resume", sid),
        }
    )
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✏️ Sửa số tiền",
                    "callback_data": build_callback(CB_INCOME, "edit", sid),
                },
                toggle_btn,
            ],
            [{
                "text": "🗑️ Xóa",
                "callback_data": build_callback(CB_INCOME, "delete", sid),
            }],
        ]
    }


def income_delete_confirm_keyboard(stream_id: uuid.UUID | str) -> InlineKeyboardMarkup:
    """Two-tap delete — accidents on the list view shouldn't lose
    a salary stream the user spent 5 taps adding."""
    sid = str(stream_id)
    return {
        "inline_keyboard": [
            [{
                "text": "🗑️ Xóa thật",
                "callback_data": build_callback(CB_INCOME, "delete_confirm", sid),
            }],
            [{
                "text": "❌ Không, giữ lại",
                "callback_data": build_callback(CB_INCOME, "list"),
            }],
        ]
    }


def income_list_footer_keyboard() -> InlineKeyboardMarkup:
    """Bottom buttons under the list view: Add new + back to menu."""
    return {
        "inline_keyboard": [
            [{
                "text": "➕ Thêm thu nhập mới",
                "callback_data": build_callback(CB_INCOME, "start"),
            }],
            [{
                "text": "◀️ Quay về menu",
                "callback_data": "menu:main",
            }],
        ]
    }
