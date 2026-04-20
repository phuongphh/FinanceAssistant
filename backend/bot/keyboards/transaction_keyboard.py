"""Inline keyboards liên quan tới 1 transaction.

Returns raw Telegram `InlineKeyboardMarkup` dicts (JSON-serialisable) vì
`backend.services.telegram_service.send_message` gửi thẳng dict qua Bot API.
"""
from backend.bot.keyboards.common import CallbackPrefix, build_callback
from backend.config.categories import get_all_categories

InlineKeyboardMarkup = dict
"""Alias for clarity — we build raw dicts matching Telegram's schema."""


def transaction_actions_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    """Keyboard xuất hiện SAU khi ghi giao dịch thành công.

    Layout:
        [🏷 Đổi danh mục] [✏️ Sửa] [🗑 Xóa]
        [↶ Hủy (5s)]
    """
    tx = str(transaction_id)
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🏷 Đổi danh mục",
                    "callback_data": build_callback(CallbackPrefix.CHANGE_CATEGORY, tx),
                },
                {
                    "text": "✏️ Sửa",
                    "callback_data": build_callback(CallbackPrefix.EDIT_TRANSACTION, tx),
                },
                {
                    "text": "🗑 Xóa",
                    "callback_data": build_callback(CallbackPrefix.DELETE_TRANSACTION, tx),
                },
            ],
            [
                {
                    "text": "↶ Hủy (5s)",
                    "callback_data": build_callback(CallbackPrefix.UNDO_TRANSACTION, tx),
                },
            ],
        ],
    }


def category_picker_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    """Keyboard hiện danh mục khi user tap 'Đổi danh mục'. 2 cột x N hàng."""
    tx = str(transaction_id)
    categories = get_all_categories()
    rows: list[list[dict]] = []

    for i in range(0, len(categories), 2):
        row = []
        for cat in categories[i : i + 2]:
            row.append(
                {
                    "text": f"{cat.emoji} {cat.name_vi}",
                    "callback_data": build_callback(
                        CallbackPrefix.CHANGE_CATEGORY, tx, cat.code
                    ),
                }
            )
        rows.append(row)

    rows.append(
        [
            {
                "text": "❌ Hủy",
                "callback_data": build_callback(CallbackPrefix.CANCEL_ACTION, tx),
            }
        ]
    )
    return {"inline_keyboard": rows}


def confirm_delete_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    """Xác nhận trước khi xóa giao dịch."""
    tx = str(transaction_id)
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Xóa",
                    "callback_data": build_callback(
                        CallbackPrefix.CONFIRM_ACTION, "delete", tx
                    ),
                },
                {
                    "text": "❌ Không",
                    "callback_data": build_callback(CallbackPrefix.CANCEL_ACTION, tx),
                },
            ]
        ],
    }
