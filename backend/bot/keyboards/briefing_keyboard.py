"""Inline keyboard for the daily morning briefing.

Callback prefix convention (matches ``backend/bot/keyboards/common.py``):

    briefing:dashboard      — open Mini App / wealth dashboard
    briefing:story          — start storytelling expense capture
    briefing:add_asset      — open the asset-add wizard
    briefing:settings       — adjust briefing time / opt out

Every button uses the ``briefing:`` prefix — including the asset-add
shortcut — so the briefing handler is the single owner of funnel
analytics. The handler then dispatches to the existing asset wizard
for ``add_asset``.
"""
from __future__ import annotations

from backend.bot.keyboards.common import build_callback

CB_BRIEFING = "briefing"

# Sub-actions, kept as constants so handlers and analytics can refer to
# the same strings (typos in callback handling are very hard to debug).
BRIEFING_ACTION_DASHBOARD = "dashboard"
BRIEFING_ACTION_STORY = "story"
BRIEFING_ACTION_ADD_ASSET = "add_asset"
BRIEFING_ACTION_SETTINGS = "settings"


def briefing_actions_keyboard() -> dict:
    """Return the inline keyboard appended to every morning briefing.

    Layout: 2x2 grid. Telegram shows two buttons per row comfortably on
    a phone (the labels are deliberately short, ≤ 16 chars each).
    """
    return {
        "inline_keyboard": [
            [
                {
                    "text": "📊 Dashboard",
                    "callback_data": build_callback(
                        CB_BRIEFING, BRIEFING_ACTION_DASHBOARD
                    ),
                },
                {
                    "text": "💬 Kể chuyện",
                    "callback_data": build_callback(
                        CB_BRIEFING, BRIEFING_ACTION_STORY
                    ),
                },
            ],
            [
                {
                    "text": "➕ Thêm tài sản",
                    "callback_data": build_callback(
                        CB_BRIEFING, BRIEFING_ACTION_ADD_ASSET
                    ),
                },
                {
                    "text": "⚙️ Đổi giờ",
                    "callback_data": build_callback(
                        CB_BRIEFING, BRIEFING_ACTION_SETTINGS
                    ),
                },
            ],
        ]
    }
