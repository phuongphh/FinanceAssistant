"""Inline keyboards for the asset-entry wizard.

Callback prefix convention (see ``backend/bot/keyboards/common.py``):

    asset_add:start                       — open type-picker
    asset_add:type:<asset_type>           — pick asset type
    asset_add:cash_subtype:<subtype>      — cash subtype pick
    asset_add:stock_subtype:<subtype>     — stock subtype pick
    asset_add:re_subtype:<subtype>        — real-estate subtype pick
    asset_add:stock_price:<same|new>      — reuse purchase price as current
    asset_add:more                        — add another asset
    asset_add:done                        — finish wizard
    asset_add:cancel                      — abort wizard

Total callback bytes stay well under Telegram's 64-byte cap.
"""
from __future__ import annotations

from backend.bot.keyboards.common import build_callback
from backend.wealth.asset_types import AssetType, get_subtypes

InlineKeyboardMarkup = dict

CB_ASSET_ADD = "asset_add"


def asset_type_picker_keyboard() -> InlineKeyboardMarkup:
    """Layout 6 asset types in a 3×2 grid for thumb-friendly tapping."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "💵 Tiền mặt / TK",
                    "callback_data": build_callback(CB_ASSET_ADD, "type", AssetType.CASH.value),
                },
                {
                    "text": "📈 Chứng khoán",
                    "callback_data": build_callback(CB_ASSET_ADD, "type", AssetType.STOCK.value),
                },
            ],
            [
                {
                    "text": "🏠 Bất động sản",
                    "callback_data": build_callback(CB_ASSET_ADD, "type", AssetType.REAL_ESTATE.value),
                },
                {
                    "text": "₿ Crypto",
                    "callback_data": build_callback(CB_ASSET_ADD, "type", AssetType.CRYPTO.value),
                },
            ],
            [
                {
                    "text": "🥇 Vàng",
                    "callback_data": build_callback(CB_ASSET_ADD, "type", AssetType.GOLD.value),
                },
                {
                    "text": "📦 Khác",
                    "callback_data": build_callback(CB_ASSET_ADD, "type", AssetType.OTHER.value),
                },
            ],
            [
                {"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")},
            ],
        ]
    }


def cash_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.CASH.value)
    rows = [
        [{
            "text": f"🏦 {subs.get('bank_savings', 'Tiết kiệm ngân hàng')}",
            "callback_data": build_callback(CB_ASSET_ADD, "cash_subtype", "bank_savings"),
        }],
        [{
            "text": f"💳 {subs.get('bank_checking', 'TK thanh toán')}",
            "callback_data": build_callback(CB_ASSET_ADD, "cash_subtype", "bank_checking"),
        }],
        [{
            "text": f"💵 {subs.get('cash', 'Tiền mặt')}",
            "callback_data": build_callback(CB_ASSET_ADD, "cash_subtype", "cash"),
        }],
        [{
            "text": f"📱 {subs.get('e_wallet', 'Ví điện tử')}",
            "callback_data": build_callback(CB_ASSET_ADD, "cash_subtype", "e_wallet"),
        }],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def stock_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.STOCK.value)
    rows = [
        [{
            "text": f"🇻🇳 {subs.get('vn_stock', 'Cổ phiếu VN')}",
            "callback_data": build_callback(CB_ASSET_ADD, "stock_subtype", "vn_stock"),
        }],
        [{
            "text": f"📊 {subs.get('fund', 'Quỹ mở')}",
            "callback_data": build_callback(CB_ASSET_ADD, "stock_subtype", "fund"),
        }],
        [{
            "text": f"📈 {subs.get('etf', 'ETF')}",
            "callback_data": build_callback(CB_ASSET_ADD, "stock_subtype", "etf"),
        }],
        [{
            "text": f"🌐 {subs.get('foreign_stock', 'Cổ phiếu nước ngoài')}",
            "callback_data": build_callback(CB_ASSET_ADD, "stock_subtype", "foreign_stock"),
        }],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def real_estate_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.REAL_ESTATE.value)
    rows = [
        [{
            "text": f"🏠 {subs.get('house_primary', 'Nhà ở')}",
            "callback_data": build_callback(CB_ASSET_ADD, "re_subtype", "house_primary"),
        }],
        [{
            "text": f"🌳 {subs.get('land', 'Đất')}",
            "callback_data": build_callback(CB_ASSET_ADD, "re_subtype", "land"),
        }],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def stock_current_price_keyboard() -> InlineKeyboardMarkup:
    """After avg purchase price, ask: same as purchase, or current?"""
    return {
        "inline_keyboard": [
            [{
                "text": "✅ Dùng giá mua",
                "callback_data": build_callback(CB_ASSET_ADD, "stock_price", "same"),
            }],
            [{
                "text": "💹 Nhập giá hiện tại",
                "callback_data": build_callback(CB_ASSET_ADD, "stock_price", "new"),
            }],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
        ]
    }


def add_more_keyboard() -> InlineKeyboardMarkup:
    """Shown after a successful asset save."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "➕ Thêm tài sản khác",
                    "callback_data": build_callback(CB_ASSET_ADD, "more"),
                },
                {
                    "text": "✅ Xong",
                    "callback_data": build_callback(CB_ASSET_ADD, "done"),
                },
            ]
        ]
    }
