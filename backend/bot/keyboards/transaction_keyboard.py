"""Inline keyboards liên quan tới 1 transaction.

Returns raw Telegram `InlineKeyboardMarkup` dicts (JSON-serialisable) vì
`backend.services.telegram_service.send_message` gửi thẳng dict qua Bot API.
"""

from backend.bot.keyboards.common import CallbackPrefix, build_callback
from backend.config.categories import get_all_categories, get_all_income_categories

InlineKeyboardMarkup = dict
"""Alias for clarity — we build raw dicts matching Telegram's schema."""


def _action_row(transaction_id: str) -> list[dict]:
    tx = str(transaction_id)
    return [
        {
            "text": "🏷",
            "callback_data": build_callback(CallbackPrefix.CHANGE_CATEGORY, tx),
        },
        {
            "text": "💳",
            "callback_data": build_callback(CallbackPrefix.CHANGE_SOURCE, tx),
        },
        {
            "text": "💵",
            "callback_data": build_callback(CallbackPrefix.EDIT_AMOUNT, tx),
        },
        {
            "text": "🗑",
            "callback_data": build_callback(CallbackPrefix.DELETE_TRANSACTION, tx),
        },
    ]


def transaction_actions_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    """Icon-only action row hiển thị sau khi ghi giao dịch thành công.

    Layout: [🏷] [💳] [💵] [🗑]
    """
    return {"inline_keyboard": [_action_row(transaction_id)]}


def transaction_actions_with_done_keyboard(
    transaction_id: str,
) -> InlineKeyboardMarkup:
    """Action row + nút ✅ Đồng ý (chỉ xuất hiện sau khi user đã sửa)."""
    tx = str(transaction_id)
    return {
        "inline_keyboard": [
            _action_row(tx),
            [
                {
                    "text": "✅ Đồng ý",
                    "callback_data": build_callback(
                        CallbackPrefix.CONFIRM_EDIT_DONE, tx
                    ),
                }
            ],
        ]
    }


def source_picker_keyboard(
    transaction_id: str, *, allow_credit_card: bool = True
) -> InlineKeyboardMarkup:
    """Picker chọn nguồn tiền khi user sửa expense (mirror category_picker).

    ``allow_credit_card=False`` hides the credit-card option for money-in
    transactions — money can never *arrive* into a credit card, so the edit
    flow must enforce the same restriction as the default-source picker.
    """
    tx = str(transaction_id)
    wallet_row: list[dict] = [
        {
            "text": "👛 Ví điện tử",
            "callback_data": build_callback(
                CallbackPrefix.CHANGE_SOURCE, tx, "wallet"
            ),
        },
    ]
    if allow_credit_card:
        wallet_row.append(
            {
                "text": "💳 Thẻ tín dụng",
                "callback_data": build_callback(
                    CallbackPrefix.CHANGE_SOURCE, tx, "card"
                ),
            }
        )
    rows: list[list[dict]] = [
        [
            {
                "text": "💵 Tiền mặt",
                "callback_data": build_callback(
                    CallbackPrefix.CHANGE_SOURCE, tx, "cash"
                ),
            },
            {
                "text": "🏦 Tài khoản",
                "callback_data": build_callback(
                    CallbackPrefix.CHANGE_SOURCE, tx, "bank"
                ),
            },
        ],
        wallet_row,
        [
            {
                "text": "❌ Hủy",
                "callback_data": build_callback(CallbackPrefix.CANCEL_ACTION, tx),
            }
        ],
    ]
    return {"inline_keyboard": rows}


def transaction_batch_actions_keyboard(batch_id: str) -> InlineKeyboardMarkup:
    """Keyboard cho confirmation nhiều giao dịch.

    Với batch, chỉ hỗ trợ undo cả nhóm để tránh đổi danh mục/sửa nhầm
    một item trong tin nhắn tổng.
    """
    return {
        "inline_keyboard": [
            [
                {
                    "text": "↶ Hủy tất cả (5s)",
                    "callback_data": build_callback(
                        CallbackPrefix.UNDO_TRANSACTION_BATCH, batch_id
                    ),
                }
            ]
        ],
    }


def category_picker_keyboard(
    transaction_id: str, *, transaction_type: str = "expense"
) -> InlineKeyboardMarkup:
    """Keyboard hiện danh mục khi user tap 'Đổi danh mục'. 2 cột x N hàng.

    Money-in transactions get the income taxonomy (Lương/Thưởng, Cổ tức…)
    rather than spending buckets, which would mis-categorize income.
    """
    tx = str(transaction_id)
    categories = (
        get_all_income_categories()
        if transaction_type == "money_in"
        else get_all_categories()
    )
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


def receipt_confirm_keyboard(
    token: str, selected_code: str | None = None
) -> InlineKeyboardMarkup:
    """Keyboard xác nhận hoá đơn OCR: lưới danh mục + 2 nút Đồng ý/Huỷ.

    Layout:
        [🍜 Ăn uống] [🚗 Di chuyển]
        ... (2 cột danh mục) ...
        [✅ Đồng ý]  [❌ Huỷ]

    ``selected_code`` (display code) được đánh dấu "✓ " để user thấy lựa
    chọn hiện tại. Khi chưa chọn (None) không cột nào được tick.
    """
    categories = get_all_categories()
    rows: list[list[dict]] = []

    for i in range(0, len(categories), 2):
        row = []
        for cat in categories[i : i + 2]:
            label = f"{cat.emoji} {cat.name_vi}"
            if selected_code and cat.code == selected_code:
                label = f"✓ {label}"
            row.append(
                {
                    "text": label,
                    "callback_data": build_callback(
                        CallbackPrefix.RECEIPT_CATEGORY, token, cat.code
                    ),
                }
            )
        rows.append(row)

    rows.append(
        [
            {"text": "✅ Đồng ý", "callback_data": f"confirm:receipt:{token}"},
            {"text": "❌ Huỷ", "callback_data": f"cancel:receipt:{token}"},
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


def transaction_source_keyboard(transaction_type: str) -> InlineKeyboardMarkup:
    """Source picker for signed manual expense/money-in syntax."""
    prefix = "txsrc"
    skip_label = (
        "Bỏ qua nguồn" if transaction_type == "expense" else "Ghi nhận không liên kết"
    )
    rows = [
        [
            {"text": "💵 Tiền mặt", "callback_data": f"{prefix}:cash"},
            {"text": "🏦 Tài khoản", "callback_data": f"{prefix}:bank_pick"},
        ],
        [{"text": "👛 Ví điện tử", "callback_data": f"{prefix}:e_wallet"}],
    ]
    if transaction_type == "expense":
        rows.append([{"text": "💳 Thẻ tín dụng", "callback_data": f"{prefix}:credit_card"}])
    rows.append([{"text": f"↪️ {skip_label}", "callback_data": f"{prefix}:skip"}])
    return {"inline_keyboard": rows}


def credit_card_source_keyboard(cards: list) -> InlineKeyboardMarkup:
    rows: list[list[dict]] = []
    for card in cards:
        rows.append([
            {
                "text": f"💳 Thẻ tín dụng - {card.bank_name}",
                "callback_data": f"txsrc_card:{card.id}",
            }
        ])
    rows.append([{"text": "↩️ Quay lại chọn nguồn", "callback_data": "txsrc:back"}])
    rows.append([{"text": "↪️ Bỏ qua nguồn", "callback_data": "txsrc:skip"}])
    return {"inline_keyboard": rows}


def e_wallet_provider_keyboard() -> InlineKeyboardMarkup:
    return {
        "inline_keyboard": [
            [
                {"text": "Momo", "callback_data": "txsrc_wallet:momo"},
                {"text": "VNPay", "callback_data": "txsrc_wallet:vnpay"},
            ],
            [
                {"text": "ZaloPay", "callback_data": "txsrc_wallet:zalopay"},
                {"text": "ViettelPay", "callback_data": "txsrc_wallet:viettelpay"},
            ],
            [{"text": "↪️ Bỏ qua nguồn", "callback_data": "txsrc:skip"}],
        ]
    }


def source_asset_keyboard(assets: list) -> InlineKeyboardMarkup:
    rows: list[list[dict]] = []
    for a in assets:
        rows.append([{"text": f"🏦 Thẻ thanh toán - {a.name}", "callback_data": f"txsrc_bank:{a.id}"}])
    rows.append([{"text": "↩️ Quay lại chọn nguồn", "callback_data": "txsrc:back"}])
    rows.append([{"text": "↪️ Bỏ qua nguồn", "callback_data": "txsrc:skip"}])
    return {"inline_keyboard": rows}
