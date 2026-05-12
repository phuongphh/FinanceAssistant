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
    asset_add:back_assets                 — abort wizard and return to Tài sản menu
    asset_add:undo:<asset_uuid>           — undo last save (hard delete)
    asset_add:rental_ask:<yes|no>         — Phase 3.8: BĐS cho thuê?
    asset_add:rental_status:<rented|vacant>  — current occupancy
    asset_add:rental_extra:<skip|add>     — collect tenant info or skip

    asset_rental:pick:<asset_uuid>        — Phase 3.8: pick existing RE asset
    asset_rental:cancel                   — abort mark-as-rental flow

    asset_manage:edit_type:<asset_type>   — list active assets filtered by type for edit
    asset_manage:edit:<uuid>:<asset_type> — edit one asset, then return to market portfolio
    asset_manage:delete_type              — choose type before delete list
    asset_manage:delete_type:<asset_type> — list active assets filtered by type
    asset_manage:delete_confirm:<uuid>    — show confirmation for one asset
    asset_manage:delete:<uuid>            — soft-delete confirmed asset
    asset_manage:cancel                   — leave manage flow

    asset:sort:<sort_key>                 — sort dashboard rows (default is value_desc)
    asset:page:<page>                     — switch dashboard page (current sort kept server-side)
    asset:edit:<asset_uuid>               — edit one asset from dashboard report
    asset:delete:<asset_uuid>             — show inline delete confirmation
    asset:delete_yes:<asset_uuid>         — confirm inline soft delete
    asset:delete_no:<sort_key>            — cancel inline delete and refresh

    asset_manage:edit_page:<asset_type>:<page>  — switch edit-list page
    asset_manage:del_page:<asset_type>:<page>   — switch delete-list page

Total callback bytes stay well under Telegram's 64-byte cap
(``asset_add:undo:`` + 36-char UUID = 51 bytes).

Pagination — every list keyboard that grows with user data MUST paginate.
Telegram silently rejects ``reply_markup`` once the serialized JSON exceeds
~10 KB (the practical client limit). At ~216 bytes per row the dashboard
keyboard hit that ceiling around 46 assets and the user saw no response.
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
CB_ASSET_MANAGE = "asset_manage"
CB_DASHBOARD = "dashboard"
CB_ASSET_ROW = "asset"

# Caps each list keyboard at ~2 KB serialized JSON — well under Telegram's
# ~10 KB practical limit and still fits within one mobile screen.
ASSET_LIST_PAGE_SIZE = 8


def clamp_page(page: int, total_items: int, page_size: int = ASSET_LIST_PAGE_SIZE) -> int:
    """Return ``page`` clamped to [0, last_page]. Empty lists return 0."""
    if total_items <= 0:
        return 0
    last = (total_items - 1) // page_size
    if page < 0:
        return 0
    if page > last:
        return last
    return page


def _page_slice(items: list, page: int, page_size: int = ASSET_LIST_PAGE_SIZE) -> tuple[list, int, int]:
    """Return ``(slice, clamped_page, total_pages)`` for a 0-indexed page."""
    total = len(items)
    if total == 0:
        return [], 0, 1
    page = clamp_page(page, total, page_size)
    total_pages = (total + page_size - 1) // page_size
    start = page * page_size
    return items[start : start + page_size], page, total_pages


def _pagination_row(
    page: int,
    total_pages: int,
    *,
    prev_cb: str,
    next_cb: str,
    label_cb: str = "asset:noop",
) -> list[dict] | None:
    """Build a ``◀ · Trang X/Y · ▶`` row. Returns ``None`` when single-page.

    ``label_cb`` is a no-op callback for the page indicator so taps don't
    trigger Telegram's "callback expired" alert.
    """
    if total_pages <= 1:
        return None
    return [
        {"text": "◀ Trước", "callback_data": prev_cb},
        {"text": f"Trang {page + 1}/{total_pages}", "callback_data": label_cb},
        {"text": "Sau ▶", "callback_data": next_cb},
    ]


def asset_type_picker_keyboard() -> InlineKeyboardMarkup:
    """Layout 6 asset types in a 3×2 grid for thumb-friendly tapping."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "💵 Tiền mặt / TK",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "type", AssetType.CASH.value
                    ),
                },
                {
                    "text": "📈 Chứng khoán",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "type", AssetType.STOCK.value
                    ),
                },
            ],
            [
                {
                    "text": "🏠 Bất động sản",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "type", AssetType.REAL_ESTATE.value
                    ),
                },
                {
                    "text": "₿ Crypto",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "type", AssetType.CRYPTO.value
                    ),
                },
            ],
            [
                {
                    "text": "🥇 Vàng",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "type", AssetType.GOLD.value
                    ),
                },
                {
                    "text": "📦 Khác",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "type", AssetType.OTHER.value
                    ),
                },
            ],
            [
                {
                    "text": "❌ Hủy",
                    "callback_data": build_callback(CB_ASSET_ADD, "cancel"),
                },
            ],
        ]
    }


def cash_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.CASH.value)
    rows = [
        [
            {
                "text": f"🏦 {subs.get('bank_savings', 'Tiết kiệm ngân hàng')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "cash_subtype", "bank_savings"
                ),
            }
        ],
        [
            {
                "text": f"💳 {subs.get('bank_checking', 'TK thanh toán')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "cash_subtype", "bank_checking"
                ),
            }
        ],
        [
            {
                "text": f"💵 {subs.get('cash', 'Tiền mặt')}",
                "callback_data": build_callback(CB_ASSET_ADD, "cash_subtype", "cash"),
            }
        ],
        [
            {
                "text": f"📱 {subs.get('e_wallet', 'Ví điện tử')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "cash_subtype", "e_wallet"
                ),
            }
        ],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def stock_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.STOCK.value)
    rows = [
        [
            {
                "text": f"🇻🇳 {subs.get('vn_stock', 'Cổ phiếu VN')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "stock_subtype", "vn_stock"
                ),
            }
        ],
        [
            {
                "text": f"📊 {subs.get('fund', 'Quỹ mở')}",
                "callback_data": build_callback(CB_ASSET_ADD, "stock_subtype", "fund"),
            }
        ],
        [
            {
                "text": f"📈 {subs.get('etf', 'ETF')}",
                "callback_data": build_callback(CB_ASSET_ADD, "stock_subtype", "etf"),
            }
        ],
        [
            {
                "text": f"🌐 {subs.get('foreign_stock', 'Cổ phiếu nước ngoài')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "stock_subtype", "foreign_stock"
                ),
            }
        ],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def crypto_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.CRYPTO.value)
    rows = [
        [
            {
                "text": f"₿ {subs.get('bitcoin', 'BTC')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "crypto_subtype", "bitcoin"
                ),
            }
        ],
        [
            {
                "text": f"♦️ {subs.get('ethereum', 'ETH')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "crypto_subtype", "ethereum"
                ),
            }
        ],
        [
            {
                "text": f"💵 {subs.get('stablecoin', 'USDT/USDC')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "crypto_subtype", "stablecoin"
                ),
            }
        ],
        [
            {
                "text": f"🪙 {subs.get('altcoin', 'Coin khác')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "crypto_subtype", "altcoin"
                ),
            }
        ],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def gold_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.GOLD.value)
    rows = [
        [
            {
                "text": f"🥇 {subs.get('sjc', 'Vàng SJC')}",
                "callback_data": build_callback(CB_ASSET_ADD, "gold_subtype", "sjc"),
            }
        ],
        [
            {
                "text": f"🏅 {subs.get('pnj', 'Vàng PNJ')}",
                "callback_data": build_callback(CB_ASSET_ADD, "gold_subtype", "pnj"),
            }
        ],
        [
            {
                "text": f"💍 {subs.get('nhan', 'Vàng nhẫn')}",
                "callback_data": build_callback(CB_ASSET_ADD, "gold_subtype", "nhan"),
            }
        ],
        [
            {
                "text": f"📿 {subs.get('trang_suc', 'Trang sức')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "gold_subtype", "trang_suc"
                ),
            }
        ],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def real_estate_subtype_keyboard() -> InlineKeyboardMarkup:
    subs = get_subtypes(AssetType.REAL_ESTATE.value)
    rows = [
        [
            {
                "text": f"🏠 {subs.get('house_primary', 'Nhà ở')}",
                "callback_data": build_callback(
                    CB_ASSET_ADD, "re_subtype", "house_primary"
                ),
            }
        ],
        [
            {
                "text": f"🌳 {subs.get('land', 'Đất')}",
                "callback_data": build_callback(CB_ASSET_ADD, "re_subtype", "land"),
            }
        ],
        [{"text": "❌ Hủy", "callback_data": build_callback(CB_ASSET_ADD, "cancel")}],
    ]
    return {"inline_keyboard": rows}


def stock_current_price_keyboard() -> InlineKeyboardMarkup:
    """After avg purchase price, ask: same as purchase, or current?"""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Dùng giá mua",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "stock_price", "same"
                    ),
                }
            ],
            [
                {
                    "text": "💹 Nhập giá hiện tại",
                    "callback_data": build_callback(CB_ASSET_ADD, "stock_price", "new"),
                }
            ],
            [
                {
                    "text": "❌ Hủy",
                    "callback_data": build_callback(CB_ASSET_ADD, "cancel"),
                }
            ],
        ]
    }


def crypto_current_price_keyboard() -> InlineKeyboardMarkup:
    """After crypto average buy price, ask for current market price."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Dùng giá mua",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "crypto_price", "same"
                    ),
                }
            ],
            [
                {
                    "text": "💹 Nhập giá hiện tại",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "crypto_price", "new"
                    ),
                }
            ],
            [
                {
                    "text": "❌ Hủy",
                    "callback_data": build_callback(CB_ASSET_ADD, "cancel"),
                }
            ],
        ]
    }


def gold_current_price_keyboard() -> InlineKeyboardMarkup:
    """After average buy price, ask for current gold price per lượng."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Dùng giá mua",
                    "callback_data": build_callback(CB_ASSET_ADD, "gold_price", "same"),
                }
            ],
            [
                {
                    "text": "💹 Nhập giá hiện tại",
                    "callback_data": build_callback(CB_ASSET_ADD, "gold_price", "new"),
                }
            ],
            [
                {
                    "text": "❌ Hủy",
                    "callback_data": build_callback(CB_ASSET_ADD, "cancel"),
                }
            ],
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
            [
                {
                    "text": "✅ Có",
                    "callback_data": build_callback(CB_ASSET_ADD, "rental_ask", "yes"),
                }
            ],
            [
                {
                    "text": "❌ Không",
                    "callback_data": build_callback(CB_ASSET_ADD, "rental_ask", "no"),
                }
            ],
            [
                {
                    "text": "◀️ Quay về",
                    "callback_data": build_callback(CB_ASSET_ADD, "back_assets"),
                }
            ],
        ]
    }


def rental_status_keyboard() -> InlineKeyboardMarkup:
    """Current occupancy status — only ``rented`` flips income on."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🏠 Đang cho thuê",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "rental_status", "rented"
                    ),
                }
            ],
            [
                {
                    "text": "🚪 Đang trống",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "rental_status", "vacant"
                    ),
                }
            ],
            [
                {
                    "text": "◀️ Quay về",
                    "callback_data": build_callback(CB_ASSET_ADD, "back_assets"),
                }
            ],
        ]
    }


def rental_extra_keyboard() -> InlineKeyboardMarkup:
    """After status=rented, offer to collect tenant name / lease dates."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "⏭️ Bỏ qua",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "rental_extra", "skip"
                    ),
                }
            ],
            [
                {
                    "text": "👤 Thêm tên người thuê",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "rental_extra", "tenant"
                    ),
                }
            ],
            [
                {
                    "text": "📅 Thêm ngày thuê",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "rental_extra", "lease"
                    ),
                }
            ],
            [
                {
                    "text": "✅ Hoàn tất",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "rental_extra", "done"
                    ),
                }
            ],
            [
                {
                    "text": "◀️ Quay về",
                    "callback_data": build_callback(CB_ASSET_ADD, "back_assets"),
                }
            ],
        ]
    }


def asset_manage_keyboard() -> InlineKeyboardMarkup:
    """Top-level asset management actions.

    Phase 3.9.5 gates destructive flows behind an explicit action and
    then a type picker, instead of dumping all assets into one long list.
    """
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🗑 Xoá tài sản",
                    "callback_data": build_callback(CB_ASSET_MANAGE, "delete_type"),
                }
            ],
            [
                {
                    "text": "➕ Thêm tài sản",
                    "callback_data": build_callback(CB_ASSET_ADD, "start"),
                }
            ],
            [
                {
                    "text": "◀️ Quay lại",
                    "callback_data": "menu:assets",
                }
            ],
        ]
    }


def asset_delete_type_keyboard() -> InlineKeyboardMarkup:
    """Choose an asset type before rendering delete rows."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "💵 Tiền mặt / TK",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "delete_type", AssetType.CASH.value
                    ),
                },
                {
                    "text": "📈 Chứng khoán",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "delete_type", AssetType.STOCK.value
                    ),
                },
            ],
            [
                {
                    "text": "🏠 Bất động sản",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "delete_type", AssetType.REAL_ESTATE.value
                    ),
                },
                {
                    "text": "₿ Crypto",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "delete_type", AssetType.CRYPTO.value
                    ),
                },
            ],
            [
                {
                    "text": "🥇 Vàng",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "delete_type", AssetType.GOLD.value
                    ),
                },
                {
                    "text": "📦 Khác",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "delete_type", AssetType.OTHER.value
                    ),
                },
            ],
            [
                {
                    "text": "◀️ Quay lại",
                    "callback_data": build_callback(CB_ASSET_MANAGE, "menu"),
                }
            ],
        ]
    }


def asset_market_manage_keyboard(asset_type: str) -> InlineKeyboardMarkup:
    """Portfolio-view actions for one market asset type."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✏️ Sửa tài sản",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "edit_type", asset_type
                    ),
                }
            ],
            [
                {
                    "text": "➕ Thêm tài sản",
                    "callback_data": build_callback(CB_ASSET_ADD, "start"),
                }
            ],
            [{"text": "◀️ Quay về Thị trường", "callback_data": "menu:market"}],
        ]
    }


def asset_edit_list_keyboard(
    candidates: list[tuple[uuid.UUID | str, str]],
    *,
    asset_type: str,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Render filtered edit rows plus navigation for market portfolio context."""
    page_items, page, total_pages = _page_slice(candidates, page)
    rows = [
        [
            {
                "text": f"✏️ {label}"[:60],
                "callback_data": build_callback(
                    CB_ASSET_MANAGE, "edit", str(asset_id), asset_type
                ),
            }
        ]
        for asset_id, label in page_items
    ]
    nav = _pagination_row(
        page,
        total_pages,
        prev_cb=build_callback(CB_ASSET_MANAGE, "edit_page", asset_type, page - 1),
        next_cb=build_callback(CB_ASSET_MANAGE, "edit_page", asset_type, page + 1),
    )
    if nav is not None:
        rows.append(nav)
    rows.append(
        [
            {
                "text": "➕ Thêm tài sản",
                "callback_data": build_callback(CB_ASSET_ADD, "start"),
            }
        ]
    )
    rows.append(
        [
            {
                "text": "◀️ Quay lại portfolio",
                "callback_data": f"menu:market:{asset_type}_portfolio",
            }
        ]
    )
    return {"inline_keyboard": rows}


def asset_delete_list_keyboard(
    candidates: list[tuple[uuid.UUID | str, str]],
    *,
    asset_type: str,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Render filtered delete rows plus navigation."""
    page_items, page, total_pages = _page_slice(candidates, page)
    rows = [
        [
            {
                "text": f"🗑 {label}"[:60],
                "callback_data": build_callback(
                    CB_ASSET_MANAGE, "delete_confirm", str(asset_id)
                ),
            }
        ]
        for asset_id, label in page_items
    ]
    nav = _pagination_row(
        page,
        total_pages,
        prev_cb=build_callback(CB_ASSET_MANAGE, "del_page", asset_type, page - 1),
        next_cb=build_callback(CB_ASSET_MANAGE, "del_page", asset_type, page + 1),
    )
    if nav is not None:
        rows.append(nav)
    rows.append(
        [
            {
                "text": "◀️ Chọn loại khác",
                "callback_data": build_callback(CB_ASSET_MANAGE, "delete_type"),
            }
        ]
    )
    rows.append(
        [
            {
                "text": "❌ Hủy",
                "callback_data": build_callback(CB_ASSET_MANAGE, "cancel"),
            }
        ]
    )
    return {"inline_keyboard": rows}


def asset_delete_confirm_keyboard(
    asset_id: uuid.UUID | str,
    *,
    asset_type: str,
) -> InlineKeyboardMarkup:
    """Final confirmation for soft-deleting an asset."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Xác nhận xoá",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "delete", str(asset_id)
                    ),
                }
            ],
            [
                {
                    "text": "◀️ Quay lại danh sách",
                    "callback_data": build_callback(
                        CB_ASSET_MANAGE, "delete_type", asset_type
                    ),
                }
            ],
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
        [
            {
                "text": label[:60],  # Telegram caps button labels at 64 bytes
                "callback_data": build_callback(CB_ASSET_RENTAL, "pick", str(asset_id)),
            }
        ]
        for asset_id, label in candidates
    ]
    rows.append(
        [
            {
                "text": "◀️ Quay về",
                "callback_data": build_callback(CB_ASSET_RENTAL, "cancel"),
            }
        ]
    )
    return {"inline_keyboard": rows}


def add_more_keyboard(
    undo_asset_id: uuid.UUID | str | None = None,
) -> InlineKeyboardMarkup:
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
        rows.append(
            [
                {
                    "text": "↩️ Huỷ tài sản vừa nhập",
                    "callback_data": build_callback(
                        CB_ASSET_ADD, "undo", str(undo_asset_id)
                    ),
                },
            ]
        )
    return {"inline_keyboard": rows}


def asset_dashboard_edit_keyboard(
    rows: list[tuple[uuid.UUID, str]],
    *,
    current_sort: str = "value_desc",
    page: int = 0,
) -> InlineKeyboardMarkup | None:
    """Sort controls plus compact edit/delete buttons per dashboard row.

    Rows are paginated at :data:`ASSET_LIST_PAGE_SIZE` per page so the
    serialized markup stays under Telegram's ~10 KB practical limit.
    """
    if not rows:
        return None

    page_items, page, total_pages = _page_slice(rows, page)

    def sort_button(key: str, label: str) -> dict:
        prefix = "✅ " if key == current_sort else ""
        return {
            "text": prefix + label,
            "callback_data": build_callback(CB_ASSET_ROW, "sort", key),
        }

    keyboard = [
        [
            sort_button("value_asc", "📉 Nhỏ→Lớn"),
            sort_button("type", "📊 Loại"),
            sort_button("alpha", "A-Z 🔤"),
        ],
    ]
    for asset_id, label in page_items:
        clean = " ".join(str(label).split())
        if len(clean) > 34:
            clean = clean[:31].rstrip() + "…"
        keyboard.append(
            [
                {
                    "text": f"✏️ {clean}",
                    "callback_data": build_callback(CB_ASSET_ROW, "edit", asset_id),
                },
                {
                    "text": "🗑️",
                    "callback_data": build_callback(CB_ASSET_ROW, "delete", asset_id),
                },
            ]
        )
    nav = _pagination_row(
        page,
        total_pages,
        prev_cb=build_callback(CB_ASSET_ROW, "page", page - 1),
        next_cb=build_callback(CB_ASSET_ROW, "page", page + 1),
    )
    if nav is not None:
        keyboard.append(nav)
    keyboard.append([{"text": "◀️ Quay về", "callback_data": "menu:assets"}])
    return {"inline_keyboard": keyboard}


def asset_dashboard_delete_confirm_keyboard(
    asset_id: uuid.UUID | str,
    *,
    current_sort: str = "value_desc",
) -> InlineKeyboardMarkup:
    """Confirmation row used by inline dashboard delete."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Xoá",
                    "callback_data": build_callback(
                        CB_ASSET_ROW, "delete_yes", asset_id
                    ),
                },
                {
                    "text": "❌ Hủy",
                    "callback_data": build_callback(
                        CB_ASSET_ROW, "delete_no", current_sort
                    ),
                },
            ]
        ]
    }
