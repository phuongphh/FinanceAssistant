"""Inline keyboards for the goals wizard (Phase 3.8 Epic 5).

Callback prefix ``goals:`` (worker dispatch picks this prefix). The
button labels stay short (≤16 chars typical) so they fit cleanly on
narrow phones.

Callbacks:
    goals:start                            — open template picker
    goals:list                             — refresh list view
    goals:template:<template_id>           — pick a template
    goals:custom                           — start custom-name input
    goals:date:<6m|1y|2y|3y|5y|custom|skip>— deadline pick
    goals:save                             — confirm save (after preview)
    goals:save_force                       — save anyway (after warning)
    goals:detail:<goal_uuid>               — open detail view
    goals:edit_progress:<goal_uuid>        — start update-progress flow
    goals:edit_amount:<goal_uuid>          — start edit-target sub-wizard
    goals:edit_date:<goal_uuid>            — start edit-date sub-wizard
    goals:delete:<goal_uuid>               — show delete confirm
    goals:delete_confirm:<goal_uuid>       — actual delete
    goals:cancel                           — abort
"""
from __future__ import annotations

import uuid

from backend.bot.keyboards.common import build_callback
from backend.services.goal_templates import list_templates

InlineKeyboardMarkup = dict

CB_GOALS = "goals"


def goals_template_keyboard() -> InlineKeyboardMarkup:
    """Show all 7 templates + "Tự tạo". Layout: 2 templates per row
    (icons make labels readable at that width), then a final row
    with "Tự tạo" + cancel."""
    templates = list_templates()
    rows: list[list[dict]] = []
    for i in range(0, len(templates), 2):
        chunk = templates[i:i + 2]
        rows.append([
            {
                "text": f"{t.icon} {t.name}",
                "callback_data": build_callback(CB_GOALS, "template", t.id),
            }
            for t in chunk
        ])
    rows.append([
        {
            "text": "✏️ Tự tạo",
            "callback_data": build_callback(CB_GOALS, "custom"),
        },
        {
            "text": "◀️ Quay về",
            "callback_data": build_callback(CB_GOALS, "cancel"),
        },
    ])
    return {"inline_keyboard": rows}


def goals_date_keyboard() -> InlineKeyboardMarkup:
    """Spec § 2.2: [6 tháng] [1 năm] [2 năm] [3 năm] [5 năm] [Tự nhập] [Bỏ qua].

    "Bỏ qua" creates an open-ended goal — projection switches to
    "if you save X/month, ETA is Y" mode. "Tự nhập" opens a date
    text-input step (YYYY-MM-DD)."""
    return {
        "inline_keyboard": [
            [
                {"text": "6 tháng", "callback_data": build_callback(CB_GOALS, "date", "6m")},
                {"text": "1 năm",   "callback_data": build_callback(CB_GOALS, "date", "1y")},
            ],
            [
                {"text": "2 năm",   "callback_data": build_callback(CB_GOALS, "date", "2y")},
                {"text": "3 năm",   "callback_data": build_callback(CB_GOALS, "date", "3y")},
            ],
            [
                {"text": "5 năm",   "callback_data": build_callback(CB_GOALS, "date", "5y")},
                {"text": "✏️ Tự nhập", "callback_data": build_callback(CB_GOALS, "date", "custom")},
            ],
            [
                {"text": "⏭️ Bỏ qua", "callback_data": build_callback(CB_GOALS, "date", "skip")},
                {"text": "◀️ Quay về", "callback_data": build_callback(CB_GOALS, "cancel")},
            ],
        ]
    }


def goals_save_keyboard() -> InlineKeyboardMarkup:
    """After the projection preview — confirm or go back."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Lưu mục tiêu",
                    "callback_data": build_callback(CB_GOALS, "save"),
                },
                {
                    "text": "📝 Sửa lại",
                    "callback_data": build_callback(CB_GOALS, "start"),
                },
            ],
            [{
                "text": "◀️ Quay về",
                "callback_data": build_callback(CB_GOALS, "cancel"),
            }],
        ]
    }


def goals_list_actions_keyboard(
    goal_id: uuid.UUID | str,
) -> InlineKeyboardMarkup:
    """Per-row buttons in the list view."""
    gid = str(goal_id)
    return {
        "inline_keyboard": [
            [
                {
                    "text": "💰 Cập nhật tiến độ",
                    "callback_data": build_callback(CB_GOALS, "edit_progress", gid),
                },
            ],
            [
                {
                    "text": "🎯 Sửa target",
                    "callback_data": build_callback(CB_GOALS, "edit_amount", gid),
                },
                {
                    "text": "📅 Sửa hạn",
                    "callback_data": build_callback(CB_GOALS, "edit_date", gid),
                },
            ],
            [{
                "text": "🗑️ Xóa",
                "callback_data": build_callback(CB_GOALS, "delete", gid),
            }],
        ]
    }


def goals_delete_confirm_keyboard(
    goal_id: uuid.UUID | str,
) -> InlineKeyboardMarkup:
    """2-tap confirm — goals take 5+ taps to set up; an accidental
    delete from the list shouldn't lose them."""
    gid = str(goal_id)
    return {
        "inline_keyboard": [
            [{
                "text": "🗑️ Xóa thật",
                "callback_data": build_callback(CB_GOALS, "delete_confirm", gid),
            }],
            [{
                "text": "❌ Không, giữ lại",
                "callback_data": build_callback(CB_GOALS, "list"),
            }],
        ]
    }


def goals_list_footer_keyboard(
    *,
    back_callback: str = "menu:main",
    back_label: str = "◀️ Quay về menu",
) -> InlineKeyboardMarkup:
    return {
        "inline_keyboard": [
            [{
                "text": "➕ Thêm mục tiêu",
                "callback_data": build_callback(CB_GOALS, "start"),
            }],
            [{"text": back_label, "callback_data": back_callback}],
        ]
    }
