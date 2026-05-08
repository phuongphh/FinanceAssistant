"""Inline keyboards for the asset-entry wizard.

Callback prefix convention (see ``backend/bot/keyboards/common.py``):

    asset_add:start                       — open type-picker
    asset_add:type:<asset_type>           — pick asset type
    asset_add:cash_subtype:<subtype>      — cash subtype pick
    asset_add:stock_subtype:<subtype>     — stock subtype pick
    asset_add:crypto_subtype:<subtype>    — crypto subtype pick
    asset_add:gold_subtype:<subtype>      — gold subtype pick
    asset_add:re_subtype:<subtype>        — real-estate subtype pick
    asset_add:stock_price:<same|new>      — reuse purchase price as current
    asset_add:crypto_price:<same|new>     — reuse purchase price as current
    asset_add:gold_price:<same|new>       — reuse purchase price as current
    asset_add:more                        — add another asset
    asset_add:done                        — finish wizard
    asset_add:cancel                      — abort wizard
    asset_add:undo:<asset_uuid>           — undo last save (hard delete)
    asset_add:rental_ask:<yes|no>         — Phase 3.8: BĐS cho thuê?
    asset_add:rental_status:<rented|vacant>  — current occupancy
    asset_add:rental_extra:<skip|add>     — collect tenant info or skip

    asset_rental:pick:<asset_uuid>        — Phase 3.8: pick existing RE asset
    asset_rental:cancel                   — abort mark-as-rental flow

Total callback bytes stay well under Telegram's 64-byte cap
(``asset_add:undo:`` + 36-char UUID = 51 bytes).
"""
from __future__ import annotations

import uuid

from backend.bot.keyboards.common import build_callback
from backend.wealth.asset_types import AssetType, get_subtypes

InlineKeyboardMarkup = dict

CB_ASSET_ADD = "asset_add"
# Separate prefix for the "mark existing real-estate as rental" flow
# so the dispatcher can route by prefix without inspecting the action.
CB_ASSET_RENTAL = "asset_rental"


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


def crypto_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.CRYPTO.value)
    rows = [
        [{
            "text": f"₿ {subs.get('bitcoin', 'BTC')}",
            "callback_data": build_callback(CB_ASSET_ADD, "crypto_subtype", "bitcoin"),
        }],
        [{
            "text": f"♦️ {subs.get('ethereum', 'ETH')}",
            "callback_data": build_callback(CB_ASSET_ADD, "crypto_subtype", "ethereum"),
        }],
        [{
            "text": f"💵 {subs.get('stablecoin', 'USDT/USDC')}",
            "callback_data": build_callback(CB_ASSET_ADD, "crypto_subtype", "stablecoin"),
        }],
        [{
            "text": f"🪙 {subs.get('altcoin', 'Coin khác')}",
            "callback_data": build_callback(CB_ASSET_ADD, "crypto_subtype", "altcoin"),
        }],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def gold_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.GOLD.value)
    rows = [
        [{
            "text": f"🥇 {subs.get('sjc', 'Vàng SJC')}",
            "callback_data": build_callback(CB_ASSET_ADD, "gold_subtype", "sjc"),
        }],
        [{
            "text": f"🏅 {subs.get('pnj', 'Vàng PNJ')}",
            "callback_data": build_callback(CB_ASSET_ADD, "gold_subtype", "pnj"),
        }],
        [{
            "text": f"💍 {subs.get('nhan', 'Vàng nhẫn')}",
            "callback_data": build_callback(CB_ASSET_ADD, "gold_subtype", "nhan"),
        }],
        [{
            "text": f"📿 {subs.get('trang_suc', 'Trang sức')}",
            "callback_data": build_callback(CB_ASSET_ADD, "gold_subtype", "trang_suc"),
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


def crypto_current_price_keyboard() -> InlineKeyboardMarkup:
    """After crypto average buy price, ask for current market price."""
    return {
        "inline_keyboard": [
            [{
                "text": "✅ Dùng giá mua",
                "callback_data": build_callback(CB_ASSET_ADD, "crypto_price", "same"),
            }],
            [{
                "text": "💹 Nhập giá hiện tại",
                "callback_data": build_callback(CB_ASSET_ADD, "crypto_price", "new"),
            }],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
        ]
    }


def gold_current_price_keyboard() -> InlineKeyboardMarkup:
    """After average buy price, ask for current gold price per lượng."""
    return {
        "inline_keyboard": [
            [{
                "text": "✅ Dùng giá mua",
                "callback_data": build_callback(CB_ASSET_ADD, "gold_price", "same"),
            }],
            [{
                "text": "💹 Nhập giá hiện tại",
                "callback_data": build_callback(CB_ASSET_ADD, "gold_price", "new"),
            }],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
        ]
    }


# ---------------------------------------------------------------------
# Phase 3.8 Epic 1 — rental sub-wizard keyboards
# ---------------------------------------------------------------------


def rental_ask_keyboard() -> InlineKeyboardMarkup:
    """Yes/No prompt asked at the end of the real-estate wizard.

    Yes path → enter the rental sub-wizard (rent → expenses → status
    → optional tenant extras). No path → save the asset as-is.
    """
    return {
        "inline_keyboard": [
            [{
                "text": "✅ Có",
                "callback_data": build_callback(CB_ASSET_ADD, "rental_ask", "yes"),
            }],
            [{
                "text": "❌ Không",
                "callback_data": build_callback(CB_ASSET_ADD, "rental_ask", "no"),
            }],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
        ]
    }


def rental_status_keyboard() -> InlineKeyboardMarkup:
    """Current occupancy status — only ``rented`` flips income on."""
    return {
        "inline_keyboard": [
            [{
                "text": "🏠 Đang cho thuê",
                "callback_data": build_callback(CB_ASSET_ADD, "rental_status", "rented"),
            }],
            [{
                "text": "🚪 Đang trống",
                "callback_data": build_callback(CB_ASSET_ADD, "rental_status", "vacant"),
            }],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
        ]
    }


def rental_extra_keyboard() -> InlineKeyboardMarkup:
    """After status=rented, offer to collect tenant name / lease dates."""
    return {
        "inline_keyboard": [
            [{
                "text": "⏭️ Bỏ qua",
                "callback_data": build_callback(CB_ASSET_ADD, "rental_extra", "skip"),
            }],
            [{
                "text": "👤 Thêm tên người thuê",
                "callback_data": build_callback(CB_ASSET_ADD, "rental_extra", "tenant"),
            }],
            [{
                "text": "📅 Thêm ngày thuê",
                "callback_data": build_callback(CB_ASSET_ADD, "rental_extra", "lease"),
            }],
            [{
                "text": "✅ Hoàn tất",
                "callback_data": build_callback(CB_ASSET_ADD, "rental_extra", "done"),
            }],
            [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
        ]
    }


def rental_pick_existing_keyboard(
    candidates: list[tuple[uuid.UUID | str, str]],
) -> InlineKeyboardMarkup:
    """Layout one button per non-rental real-estate asset.

    ``candidates`` = ``[(asset_id, label), ...]``. Empty list → caller
    sends an "empty state" message rather than rendering a useless
    keyboard.
    """
    rows = [
        [{
            "text": label[:60],  # Telegram caps button labels at 64 bytes
            "callback_data": build_callback(CB_ASSET_RENTAL, "pick", str(asset_id)),
        }]
        for asset_id, label in candidates
    ]
    rows.append([{
        "text": "❌ Hủy",
        "callback_data": build_callback(CB_ASSET_RENTAL, "cancel"),
    }])
    return {"inline_keyboard": rows}


def add_more_keyboard(undo_asset_id: uuid.UUID | str | None = None) -> InlineKeyboardMarkup:
    """Shown after a successful asset save.

    If ``undo_asset_id`` is given, an extra "↩️ Huỷ" row appears so the
    user can revert a mis-entered asset. The id is embedded in the
    callback (``asset_add:undo:<uuid>``) so the handler knows exactly
    which row to roll back without trusting state from elsewhere.
    """
    rows = [
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
    if undo_asset_id is not None:
        rows.append([
            {
                "text": "↩️ Huỷ tài sản vừa nhập",
                "callback_data": build_callback(CB_ASSET_ADD, "undo", str(undo_asset_id)),
            },
        ])
    return {"inline_keyboard": rows}
