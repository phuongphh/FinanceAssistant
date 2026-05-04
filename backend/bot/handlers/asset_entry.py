"""Asset-entry wizard handler.

Three flows — cash, stock, real-estate — share a common entry point and
dispatcher. State lives on ``users.wizard_state`` (JSONB) so the bot
can survive process restarts mid-wizard.

Flow names (stored in ``wizard_state.flow``):

    asset_add_cash         — 2 questions: subtype → "name + amount"
    asset_add_stock        — 4 questions: subtype → ticker → quantity
                             → avg_price → (same|new current_price)
    asset_add_real_estate  — 4 questions: subtype → name → initial_value
                             → current_value

Each step name (``wizard_state.step``) is checked by the worker so the
NL expense parser doesn't swallow text that should advance the wizard.

All callbacks come in via ``handle_asset_callback`` (returns True if
handled). All free-text replies come in via ``handle_asset_text_input``
(returns True if consumed by an active wizard step).

Layer contract: this handler reads/mutates DB through services
(``wizard_service``, ``asset_service``, ``net_worth_calculator``) and
never commits — the worker owns the transaction boundary.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.money import format_money_short
from backend.bot.formatters.wealth_formatter import format_asset_added, format_asset_list
from backend.bot.keyboards.asset_keyboard import (
    add_more_keyboard,
    asset_type_picker_keyboard,
    cash_subtype_keyboard,
    real_estate_subtype_keyboard,
    stock_current_price_keyboard,
    stock_subtype_keyboard,
)
from backend.bot.keyboards.common import parse_callback
from backend.models.user import User
from backend.services import wizard_service
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    answer_callback,
    edit_message_text,
    send_message,
)
from backend.wealth.amount_parser import (
    has_negative_sign,
    parse_amount,
    parse_label_and_amount,
)
from backend.wealth.asset_types import AssetType, get_subtypes
from backend.wealth.fx import USD_VND_RATE, parse_usd_amount, usd_to_vnd
from backend.wealth.ladder import update_user_level
from backend.wealth.services import asset_service, net_worth_calculator

logger = logging.getLogger(__name__)


class AssetEvent:
    """Analytics event names for the asset-entry funnel."""
    WIZARD_OPENED = "asset_wizard_opened"
    TYPE_PICKED = "asset_wizard_type_picked"
    ASSET_ADDED = "asset_added"
    ASSET_UNDONE = "asset_undone"
    WIZARD_CANCELED = "asset_wizard_canceled"
    PARSE_FAILED = "asset_wizard_parse_failed"


# Flow names persisted in wizard_state.
# All start with "asset_add" so the text dispatcher can detect "user is mid
# asset-wizard" with a single prefix check (see ``handle_asset_text_input``).
FLOW_PICKER = "asset_add_picker"  # 6-button type picker shown, nothing chosen
FLOW_CASH = "asset_add_cash"
FLOW_STOCK = "asset_add_stock"
FLOW_REAL_ESTATE = "asset_add_real_estate"


# ---------- Entry point ----------------------------------------------

async def start_asset_wizard(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Show the 6-button asset-type picker. First step of every flow.

    Sets ``wizard_state`` to a picker sentinel rather than clearing it, so
    that text typed while the picker (or a downstream subtype keyboard) is
    on screen gets caught by ``handle_asset_text_input`` and answered with
    a "tap a button" nudge — instead of falling through to the NL expense
    parser and being silently saved as a transaction.
    """
    await wizard_service.start_flow(
        db, user.id, FLOW_PICKER, step="type", draft={},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            "💎 <b>Thêm tài sản mới</b>\n\n"
            "Loại tài sản nào bạn muốn thêm?"
        ),
        parse_mode="HTML",
        reply_markup=asset_type_picker_keyboard(),
    )
    analytics.track(AssetEvent.WIZARD_OPENED, user_id=user.id)


async def cancel_wizard(
    db: AsyncSession, chat_id: int, user: User
) -> bool:
    """Clear an active asset-wizard state and acknowledge.

    Returns True if there was an asset wizard to cancel. Used by the
    ``/huy`` and ``/cancel`` commands so the user has a text-based escape
    hatch in addition to the inline ❌ Hủy button.
    """
    flow = (user.wizard_state or {}).get("flow") or ""
    if not flow.startswith("asset_add"):
        return False
    await wizard_service.clear(db, user.id)
    analytics.track(AssetEvent.WIZARD_CANCELED, user_id=user.id)
    await send_message(
        chat_id=chat_id, text="Đã huỷ. Quay lại lúc nào cũng được 👋"
    )
    return True


async def list_assets(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Handle /taisan — display all active assets for the user."""
    assets = await asset_service.get_user_assets(db, user.id)
    await send_message(
        chat_id=chat_id,
        text=format_asset_list(assets),
        parse_mode="HTML",
    )


# ---------- Cash flow -------------------------------------------------

_CASH_SUBTYPE_PROMPTS: dict[str, tuple[str, str]] = {
    "bank_savings": (
        "Tên ngân hàng + số tiền trong tài khoản tiết kiệm",
        "Ví dụ: <code>VCB 100 triệu</code> hoặc <code>Techcom 50tr</code>",
    ),
    "bank_checking": (
        "Tên ngân hàng + số dư tài khoản thanh toán",
        "Ví dụ: <code>MB 15tr</code>",
    ),
    "cash": (
        "Số tiền mặt bạn đang giữ",
        "Ví dụ: <code>5 triệu</code>",
    ),
    "e_wallet": (
        "Tên ví + số dư",
        "Ví dụ: <code>MoMo 2tr</code> hoặc <code>ZaloPay 500k</code>",
    ),
}


async def _start_cash_subtype_pick(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    await wizard_service.start_flow(
        db, user.id, FLOW_CASH, step="subtype",
        draft={"asset_type": AssetType.CASH.value},
    )
    await send_message(
        chat_id=chat_id,
        text="💵 Tiền của bạn đang ở đâu?",
        parse_mode="HTML",
        reply_markup=cash_subtype_keyboard(),
    )


async def _handle_cash_subtype_pick(
    db: AsyncSession, chat_id: int, user: User, subtype: str
) -> None:
    subs = get_subtypes(AssetType.CASH.value)
    if subtype not in subs:
        await send_message(chat_id=chat_id, text="Loại không hợp lệ.")
        return

    await wizard_service.update_step(
        db, user.id, step="amount", draft_patch={"subtype": subtype},
    )
    label_prompt, example = _CASH_SUBTYPE_PROMPTS[subtype]
    await send_message(
        chat_id=chat_id,
        text=f"💬 {label_prompt}\n\n{example}",
        parse_mode="HTML",
    )


async def _handle_cash_amount_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(
            chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂"
        )
        return

    parsed = parse_label_and_amount(text)
    if not parsed:
        analytics.track(
            AssetEvent.PARSE_FAILED,
            user_id=user.id,
            properties={"flow": FLOW_CASH},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "Mình chưa hiểu lắm 😅\n"
                "Bạn thử lại theo format <b>Tên + số tiền</b> nhé?\n"
                "Ví dụ: <code>VCB 100 triệu</code>"
            ),
            parse_mode="HTML",
        )
        return

    label, amount = parsed
    if amount <= 0:
        await send_message(
            chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂"
        )
        return

    name = label or {
        "bank_savings": "Tài khoản tiết kiệm",
        "bank_checking": "Tài khoản thanh toán",
        "cash": "Tiền mặt",
        "e_wallet": "Ví điện tử",
    }.get(draft.get("subtype", ""), "Tài khoản")

    asset = await asset_service.create_asset(
        db, user.id,
        asset_type=AssetType.CASH.value,
        subtype=draft.get("subtype"),
        name=name,
        initial_value=amount,
    )
    await _post_save(db, chat_id, user, asset)


# ---------- Stock flow ------------------------------------------------

def _stock_unit_label(subtype: str | None) -> str:
    """Human-readable unit name shown in stock-flow prompts.

    Funds trade in "chứng chỉ quỹ" (CCQ); everything else (VN stock,
    ETF, foreign stock) trades in "cổ phiếu". The two subtypes share
    the same wizard but the user-facing wording must match.
    """
    if subtype == "fund":
        return "chứng chỉ quỹ"
    return "cổ phiếu"


def _stock_unit_short(subtype: str | None) -> str:
    """Short suffix for per-unit prices, e.g. ``45,000đ/cp`` vs ``/ccq``."""
    if subtype == "fund":
        return "ccq"
    return "cp"


def _format_usd(amount: Decimal) -> str:
    """Format a USD amount with US thousands separators and 2 decimals.

    Drops the trailing ``.00`` on whole-dollar amounts so ``$150`` reads
    cleaner than ``$150.00`` in the typical foreign-stock case.
    """
    value = float(amount)
    if value == int(value):
        return f"${int(value):,}"
    return f"${value:,.2f}"


async def _start_stock_subtype_pick(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    await wizard_service.start_flow(
        db, user.id, FLOW_STOCK, step="subtype",
        draft={"asset_type": AssetType.STOCK.value, "extra": {}},
    )
    await send_message(
        chat_id=chat_id,
        text="📈 Loại đầu tư nào?",
        parse_mode="HTML",
        reply_markup=stock_subtype_keyboard(),
    )


async def _handle_stock_subtype_pick(
    db: AsyncSession, chat_id: int, user: User, subtype: str
) -> None:
    subs = get_subtypes(AssetType.STOCK.value)
    if subtype not in subs:
        await send_message(chat_id=chat_id, text="Loại không hợp lệ.")
        return

    extra: dict = {}
    if subtype == "vn_stock":
        extra["exchange"] = "HOSE"
    elif subtype == "foreign_stock":
        # Foreign-stock prices are entered in USD; record the rate snapshot
        # at wizard time so historical values can be back-traced if the
        # mid-rate gets updated later.
        extra["currency"] = "USD"
        extra["fx_rate_vnd"] = float(USD_VND_RATE)

    await wizard_service.update_step(
        db, user.id, step="ticker",
        draft_patch={"subtype": subtype, "extra": extra},
    )
    examples = {
        "vn_stock": "<code>VNM</code>, <code>VIC</code>, <code>HPG</code>",
        "etf": "<code>E1VFVN30</code>, <code>FUEVFVND</code>",
        "fund": "<code>VESAF</code>, <code>VEOF</code>, <code>DCDS</code>",
        "foreign_stock": "<code>AAPL</code>, <code>GOOGL</code>, <code>NVDA</code>",
    }.get(subtype, "<code>VNM</code>, <code>VIC</code>, <code>HPG</code>")
    await send_message(
        chat_id=chat_id,
        text=(
            "📈 <b>Mã (ticker) là gì?</b>\n\n"
            f"Ví dụ: {examples}"
        ),
        parse_mode="HTML",
    )


async def _handle_stock_ticker_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    # Normalise: "VNM stocks" → "VNM", strip whitespace, uppercase.
    ticker = text.strip().split()[0].upper() if text.strip() else ""
    if not ticker.isalnum() or len(ticker) > 10:
        await send_message(
            chat_id=chat_id,
            text="Mã ticker thường là 3-4 chữ cái. Bạn nhập lại nhé.",
        )
        return

    extra = dict(draft.get("extra") or {})
    extra["ticker"] = ticker
    await wizard_service.update_step(
        db, user.id, step="quantity",
        draft_patch={"extra": extra, "name": ticker},
    )
    unit = _stock_unit_label(draft.get("subtype"))
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>{ticker}</b>\n\n"
            f"Bạn đang sở hữu bao nhiêu {unit}?"
        ),
        parse_mode="HTML",
    )


async def _handle_stock_quantity_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    cleaned = text.strip().replace(",", "").replace(".", "").replace(" ", "")
    if not cleaned.isdigit():
        await send_message(
            chat_id=chat_id,
            text="Nhập số nguyên thôi nhé. Ví dụ: <code>100</code>",
            parse_mode="HTML",
        )
        return

    quantity = int(cleaned)
    if quantity <= 0:
        await send_message(chat_id=chat_id, text="Số lượng phải lớn hơn 0.")
        return

    extra = dict(draft.get("extra") or {})
    extra["quantity"] = quantity
    await wizard_service.update_step(
        db, user.id, step="avg_price", draft_patch={"extra": extra},
    )
    subtype = draft.get("subtype")
    unit = _stock_unit_label(subtype)
    if subtype == "foreign_stock":
        prompt = (
            f"✅ <b>{quantity:,}</b> {unit}\n\n"
            f"Giá mua trung bình mỗi {unit} (USD)?\n"
            "Ví dụ: <code>150</code> hoặc <code>150.5</code>"
        )
    elif subtype == "fund":
        prompt = (
            f"✅ <b>{quantity:,}</b> {unit}\n\n"
            f"Giá mua trung bình 1 {unit}?\n"
            "Ví dụ: <code>15000</code> hoặc <code>15k</code>"
        )
    else:
        prompt = (
            f"✅ <b>{quantity:,}</b> {unit}\n\n"
            f"Giá mua trung bình mỗi {unit}?\n"
            "Ví dụ: <code>45000</code> hoặc <code>45k</code>"
        )
    await send_message(chat_id=chat_id, text=prompt, parse_mode="HTML")


async def _handle_stock_avg_price_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(
            chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂"
        )
        return

    subtype = draft.get("subtype")
    is_foreign = subtype == "foreign_stock"
    unit = _stock_unit_label(subtype)
    unit_short = _stock_unit_short(subtype)

    if is_foreign:
        avg_price_usd = parse_usd_amount(text)
        avg_price_vnd = usd_to_vnd(avg_price_usd) if avg_price_usd is not None else None
    else:
        avg_price_usd = None
        avg_price_vnd = parse_amount(text)

    if avg_price_vnd is None or avg_price_vnd <= 0:
        analytics.track(AssetEvent.PARSE_FAILED, user_id=user.id,
                        properties={"flow": FLOW_STOCK, "field": "avg_price"})
        example = (
            "Ví dụ: <code>150</code> hoặc <code>150.5</code> (USD)"
            if is_foreign else
            "Ví dụ: <code>45000</code> hoặc <code>45k</code>"
        )
        await send_message(
            chat_id=chat_id,
            text=f"Nhập giá giúp mình nhé 🙏\n{example}",
            parse_mode="HTML",
        )
        return

    extra = dict(draft.get("extra") or {})
    # ``avg_price`` is canonical VND-per-unit so downstream readers
    # (Mini App, briefing) don't need to know the source currency.
    extra["avg_price"] = float(avg_price_vnd)
    if avg_price_usd is not None:
        extra["avg_price_usd"] = float(avg_price_usd)
    quantity = extra.get("quantity", 0)
    initial_value = avg_price_vnd * quantity

    await wizard_service.update_step(
        db, user.id, step="current_price",
        draft_patch={"extra": extra, "initial_value": float(initial_value)},
    )

    if is_foreign:
        initial_usd = avg_price_usd * Decimal(quantity)
        confirm = (
            f"✅ Giá mua TB: <b>{_format_usd(avg_price_usd)}/{unit_short}</b>\n"
            f"Tổng vốn: <b>{_format_usd(initial_usd)}</b> "
            f"(~{format_money_short(initial_value)} VNĐ tạm tính)\n"
            f"FX: {int(USD_VND_RATE):,} VND/USD\n\n"
            f"Giá hiện tại của 1 {unit} là bao nhiêu (USD)?\n"
            "(Hoặc dùng giá mua nếu không nhớ)"
        )
    else:
        confirm = (
            f"✅ Giá mua TB: <b>{int(avg_price_vnd):,}đ/{unit_short}</b>\n"
            f"Tổng vốn: <b>{int(initial_value):,}đ</b>\n\n"
            f"Giá hiện tại của 1 {unit} là bao nhiêu?\n"
            "(Hoặc dùng giá mua nếu không nhớ)"
        )
    await send_message(
        chat_id=chat_id,
        text=confirm,
        parse_mode="HTML",
        reply_markup=stock_current_price_keyboard(),
    )


async def _handle_stock_current_price_choice(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict
) -> None:
    subtype = draft.get("subtype")
    if choice == "same":
        # "Use purchase price" reuses whatever was captured during the
        # avg_price step — VND for domestic flows, USD-derived VND for
        # foreign. ``_save_stock_asset`` re-derives both.
        avg_price_vnd = Decimal(str(draft.get("extra", {}).get("avg_price") or 0))
        await _save_stock_asset(db, chat_id, user, draft, avg_price_vnd)
    elif choice == "new":
        await wizard_service.update_step(db, user.id, step="current_price_input")
        unit = _stock_unit_label(subtype)
        if subtype == "foreign_stock":
            prompt = (
                f"💹 Nhập giá hiện tại của 1 {unit} (USD):\n"
                "Ví dụ: <code>165</code>"
            )
        elif subtype == "fund":
            prompt = (
                f"💹 Nhập giá hiện tại của 1 {unit}:\n"
                "Ví dụ: <code>16000</code>"
            )
        else:
            prompt = (
                f"💹 Nhập giá hiện tại của 1 {unit}:\n"
                "Ví dụ: <code>52000</code>"
            )
        await send_message(chat_id=chat_id, text=prompt, parse_mode="HTML")


async def _handle_stock_current_price_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(
            chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂"
        )
        return

    subtype = draft.get("subtype")
    is_foreign = subtype == "foreign_stock"

    if is_foreign:
        current_price_usd = parse_usd_amount(text)
        current_price_vnd = (
            usd_to_vnd(current_price_usd) if current_price_usd is not None else None
        )
    else:
        current_price_usd = None
        current_price_vnd = parse_amount(text)

    if current_price_vnd is None or current_price_vnd <= 0:
        example = (
            "Ví dụ: <code>165</code> (USD)" if is_foreign
            else "Ví dụ: <code>52000</code>"
        )
        await send_message(
            chat_id=chat_id,
            text=f"Nhập giá giúp mình nhé. {example}",
            parse_mode="HTML",
        )
        return

    if current_price_usd is not None:
        # Stash the USD figure on the draft so ``_save_stock_asset``
        # records it alongside the converted VND.
        extra = dict(draft.get("extra") or {})
        extra["current_price_usd"] = float(current_price_usd)
        draft["extra"] = extra

    await _save_stock_asset(db, chat_id, user, draft, current_price_vnd)


async def _save_stock_asset(
    db: AsyncSession, chat_id: int, user: User, draft: dict, current_price: Decimal
) -> None:
    extra = dict(draft.get("extra") or {})
    quantity = Decimal(str(extra.get("quantity") or 0))
    avg_price = Decimal(str(extra.get("avg_price") or 0))
    initial_value = avg_price * quantity
    current_value = current_price * quantity
    name = draft.get("name") or extra.get("ticker", "Cổ phiếu")

    # For foreign stocks: persist the USD-side numbers and the FX rate
    # used, so the confirmation message and any future Mini-App detail
    # view can show "$1,500 ≈ 37.5tr tạm tính" without re-deriving.
    if extra.get("currency") == "USD":
        avg_price_usd = Decimal(str(extra.get("avg_price_usd") or 0))
        current_price_usd = Decimal(str(
            extra.get("current_price_usd") if extra.get("current_price_usd") is not None
            else extra.get("avg_price_usd") or 0
        ))
        extra["current_price_usd"] = float(current_price_usd)
        extra["initial_value_usd"] = float(avg_price_usd * quantity)
        extra["current_value_usd"] = float(current_price_usd * quantity)
        extra["current_price"] = float(current_price)

    asset = await asset_service.create_asset(
        db, user.id,
        asset_type=AssetType.STOCK.value,
        subtype=draft.get("subtype"),
        name=name,
        initial_value=initial_value,
        current_value=current_value,
        extra=extra,
    )
    await _post_save(db, chat_id, user, asset)


# ---------- Real estate flow ------------------------------------------

_RENTAL_HINT_WORDS = ("cho thuê", "thuê tháng", "tenant", "rental")


async def _start_real_estate_subtype_pick(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    await wizard_service.start_flow(
        db, user.id, FLOW_REAL_ESTATE, step="subtype",
        draft={"asset_type": AssetType.REAL_ESTATE.value, "extra": {}},
    )
    await send_message(
        chat_id=chat_id,
        text="🏠 Loại bất động sản nào?",
        parse_mode="HTML",
        reply_markup=real_estate_subtype_keyboard(),
    )


async def _handle_re_subtype_pick(
    db: AsyncSession, chat_id: int, user: User, subtype: str
) -> None:
    subs = get_subtypes(AssetType.REAL_ESTATE.value)
    if subtype not in subs:
        await send_message(chat_id=chat_id, text="Loại không hợp lệ.")
        return
    await wizard_service.update_step(
        db, user.id, step="name", draft_patch={"subtype": subtype},
    )
    examples = {
        "house_primary": "Nhà Mỹ Đình",
        "land": "Đất Ba Vì",
    }
    await send_message(
        chat_id=chat_id,
        text=(
            "🏷 <b>Đặt tên cho BĐS này</b>\n\n"
            f"Ví dụ: <code>{examples.get(subtype, 'Nhà 1')}</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_re_name_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    name = text.strip()
    if not name or len(name) > 200:
        await send_message(chat_id=chat_id, text="Tên BĐS từ 1-200 ký tự nhé.")
        return

    if any(word in name.lower() for word in _RENTAL_HINT_WORDS):
        await send_message(
            chat_id=chat_id,
            text=(
                "ℹ️ Mình ghi nhận. Tính năng <b>cho thuê</b> "
                "(track tenant, dòng tiền) sẽ có ở Phase 4 — "
                "tạm thời mình lưu như BĐS thường nhé."
            ),
            parse_mode="HTML",
        )

    await wizard_service.update_step(
        db, user.id, step="initial_value", draft_patch={"name": name},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            "💰 <b>Giá mua / vốn ban đầu</b> là bao nhiêu?\n\n"
            "Ví dụ: <code>2 tỷ</code>, <code>2.5 tỷ</code>, "
            "<code>2500tr</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_re_initial_value_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(
            chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂"
        )
        return
    amount = parse_amount(text)
    if amount is None or amount <= 0:
        analytics.track(AssetEvent.PARSE_FAILED, user_id=user.id,
                        properties={"flow": FLOW_REAL_ESTATE, "field": "initial_value"})
        await send_message(
            chat_id=chat_id,
            text="Nhập giá giúp mình. Ví dụ: <code>2 tỷ</code>",
            parse_mode="HTML",
        )
        return

    await wizard_service.update_step(
        db, user.id, step="current_value",
        draft_patch={"initial_value": float(amount)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Vốn gốc: <b>{int(amount):,}đ</b>\n\n"
            "💎 <b>Giá ước tính hiện tại</b>?\n"
            "(Nếu không chắc, dùng giá mua cũng được — "
            "bạn có thể update sau.)"
        ),
        parse_mode="HTML",
    )


async def _handle_re_current_value_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(
            chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂"
        )
        return
    current = parse_amount(text)
    if current is None or current <= 0:
        await send_message(
            chat_id=chat_id,
            text="Nhập giá giúp mình. Ví dụ: <code>2.5 tỷ</code>",
            parse_mode="HTML",
        )
        return

    initial = Decimal(str(draft.get("initial_value") or 0))
    if initial <= 0:
        initial = current

    extra = dict(draft.get("extra") or {})
    asset = await asset_service.create_asset(
        db, user.id,
        asset_type=AssetType.REAL_ESTATE.value,
        subtype=draft.get("subtype"),
        name=draft.get("name") or "Bất động sản",
        initial_value=initial,
        current_value=current,
        extra=extra,
    )
    await send_message(
        chat_id=chat_id,
        text=(
            "💡 Bạn có thể update giá trị BĐS bất cứ lúc nào "
            "khi thị trường biến động."
        ),
    )
    await _post_save(db, chat_id, user, asset)


# ---------- Save / cleanup --------------------------------------------

async def _post_save(
    db: AsyncSession, chat_id: int, user: User, asset
) -> None:
    """Finalise: clear wizard, recompute net worth, update wealth level,
    track analytics, and prompt for the next action."""
    await wizard_service.clear(db, user.id)

    breakdown = await net_worth_calculator.calculate(db, user.id)
    new_level = await update_user_level(db, user.id, breakdown.total)

    analytics.track(
        AssetEvent.ASSET_ADDED,
        user_id=user.id,
        properties={
            "asset_type": asset.asset_type,
            "subtype": asset.subtype,
            "asset_count": breakdown.asset_count,
        },
    )
    if new_level is not None:
        analytics.track(
            "wealth_level_up",
            user_id=user.id,
            properties={"level": new_level.value},
        )

    await send_message(
        chat_id=chat_id,
        text=format_asset_added(asset, breakdown.total),
        parse_mode="HTML",
    )
    await send_message(
        chat_id=chat_id,
        text="Tiếp tục thêm tài sản, hay xong rồi?",
        reply_markup=add_more_keyboard(undo_asset_id=asset.id),
    )


async def _handle_undo(
    db: AsyncSession, chat_id: int, user: User, asset_id_str: str
) -> None:
    """Hard-delete the asset referenced by the undo button.

    Distinct from ``soft_delete`` (which is for sales): the user is
    saying "I never meant to add this", so we remove it cleanly.
    The undo callback embeds the asset id so we don't have to trust
    "the most recent asset" — concurrent edits can't trick us.
    """
    try:
        asset_uuid = uuid.UUID(asset_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản để huỷ.")
        return

    asset = await asset_service.get_asset_by_id(db, user.id, asset_uuid)
    if asset is None:
        await send_message(
            chat_id=chat_id,
            text="Tài sản này đã được xử lý rồi 🤔",
        )
        return

    asset_name = asset.name
    deleted = await asset_service.hard_delete(db, user.id, asset_uuid)
    if not deleted:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản để huỷ.")
        return

    breakdown = await net_worth_calculator.calculate(db, user.id)
    await update_user_level(db, user.id, breakdown.total)

    analytics.track(
        AssetEvent.ASSET_UNDONE,
        user_id=user.id,
        properties={"asset_id": str(asset_uuid)},
    )

    await send_message(
        chat_id=chat_id,
        text=f"↩️ Đã huỷ <b>{asset_name}</b>. Tổng tài sản đã được cập nhật.",
        parse_mode="HTML",
    )


# ---------- Public dispatch ------------------------------------------

# Map (flow, step) → handler. Handlers signature:
#   async (db, chat_id, user, text, draft) -> None
_TEXT_DISPATCH = {
    (FLOW_CASH, "amount"): _handle_cash_amount_input,
    (FLOW_STOCK, "ticker"): _handle_stock_ticker_input,
    (FLOW_STOCK, "quantity"): _handle_stock_quantity_input,
    (FLOW_STOCK, "avg_price"): _handle_stock_avg_price_input,
    (FLOW_STOCK, "current_price_input"): _handle_stock_current_price_input,
    (FLOW_REAL_ESTATE, "name"): _handle_re_name_input,
    (FLOW_REAL_ESTATE, "initial_value"): _handle_re_initial_value_input,
    (FLOW_REAL_ESTATE, "current_value"): _handle_re_current_value_input,
}


async def handle_asset_text_input(
    db: AsyncSession, message: dict
) -> bool:
    """Consume free text if the user is mid-wizard. Return True if so.

    Returns True for *any* asset-wizard flow — including the picker /
    subtype / stock-price-choice steps that don't accept text input. In
    those cases we send a "tap a button" nudge rather than letting the
    text fall through to the NL expense parser, which would silently
    record it as a transaction. The previous behaviour caused a real
    incident: user tapped "+Thêm tài sản khác" then typed
    "VCB-002 20 triệu" without picking a subtype, and the bot saved it
    as an expense (see commit message / PR).
    """
    text = (message.get("text") or "").strip()
    if not text or text.startswith("/"):
        return False

    chat_id = message["chat"]["id"]
    telegram_id = (message.get("from") or {}).get("id")
    if telegram_id is None:
        return False

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None or not user.wizard_state:
        return False

    flow = wizard_service.get_flow(user.wizard_state)
    step = wizard_service.get_step(user.wizard_state)

    # Only intercept asset-wizard flows. Storytelling and any future
    # wizards have their own routers earlier in the dispatch chain.
    if not (flow or "").startswith("asset_add"):
        return False

    handler = _TEXT_DISPATCH.get((flow, step))
    if handler is None:
        # Wizard is at a step that expects a button tap, not free text.
        # Consume the text with a nudge so it can't reach the NL expense
        # parser and be misclassified.
        analytics.track(
            AssetEvent.PARSE_FAILED,
            user_id=user.id,
            properties={"flow": flow, "step": step, "reason": "text_at_button_step"},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "👆 Bạn đang trong wizard <b>thêm tài sản</b> — "
                "vui lòng tap nút phía trên (hoặc ❌ Hủy / gõ /huy để thoát)."
            ),
            parse_mode="HTML",
        )
        return True

    draft = wizard_service.get_draft(user.wizard_state)
    try:
        await handler(db, chat_id, user, text, draft)
    except Exception:
        logger.exception("asset wizard text handler crashed: flow=%s step=%s",
                         flow, step)
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id,
            text="Có lỗi xảy ra, mình huỷ wizard. Thử lại bằng /assets nhé.",
        )
    return True


async def _dispatch_asset_action(
    db: AsyncSession,
    chat_id: int,
    user: User,
    action: str,
    arg: str | None,
) -> None:
    """Body of the asset-callback dispatcher.

    Split out from ``handle_asset_callback`` so we can run it in parallel
    with ``answer_callback`` via ``asyncio.gather`` — Telegram needs the
    callback acked to dismiss the loading spinner, but that ack is
    independent of any send_message/edit_message_text the action produces.
    Running them sequentially paid one full RTT to api.telegram.org for
    no business reason; gather halves perceived latency on every tap.
    """
    # Top-level entry / restart.
    if action == "start" or (action == "more"):
        await start_asset_wizard(db, chat_id, user)
        return

    if action == "cancel":
        await wizard_service.clear(db, user.id)
        analytics.track(AssetEvent.WIZARD_CANCELED, user_id=user.id)
        await send_message(chat_id=chat_id, text="Đã huỷ. Quay lại lúc nào cũng được 👋")
        return

    if action == "undo" and arg:
        await _handle_undo(db, chat_id, user, arg)
        return

    if action == "done":
        await wizard_service.clear(db, user.id)
        # Mark first-asset onboarding step done if this was their first asset.
        await _mark_onboarding_first_asset_done(db, user)
        await send_message(
            chat_id=chat_id,
            text="✅ Xong! Gõ /menu để xem các tính năng khác.",
        )
        return

    if action == "type" and arg:
        analytics.track(
            AssetEvent.TYPE_PICKED,
            user_id=user.id,
            properties={"asset_type": arg},
        )
        starters = {
            AssetType.CASH.value: _start_cash_subtype_pick,
            AssetType.STOCK.value: _start_stock_subtype_pick,
            AssetType.REAL_ESTATE.value: _start_real_estate_subtype_pick,
        }
        starter = starters.get(arg)
        if starter is None:
            # Crypto / Gold / Other: not yet wired in Epic 1.
            await send_message(
                chat_id=chat_id,
                text=(
                    "Loại này sẽ có sớm 🙏 Tạm thời bạn dùng "
                    "💵 / 📈 / 🏠 nhé."
                ),
            )
            return
        await starter(db, chat_id, user)
        return

    if action == "cash_subtype" and arg:
        await _handle_cash_subtype_pick(db, chat_id, user, arg)
        return

    if action == "stock_subtype" and arg:
        await _handle_stock_subtype_pick(db, chat_id, user, arg)
        return

    if action == "re_subtype" and arg:
        await _handle_re_subtype_pick(db, chat_id, user, arg)
        return

    if action == "stock_price" and arg in ("same", "new"):
        draft = wizard_service.get_draft(user.wizard_state)
        await _handle_stock_current_price_choice(db, chat_id, user, arg, draft)
        return


async def handle_asset_callback(
    db: AsyncSession, callback_query: dict
) -> bool:
    """Route any ``asset_add:*`` callback. Returns True if handled."""
    data: str = callback_query.get("data") or ""
    if not data.startswith("asset_add"):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    telegram_id = (callback_query.get("from") or {}).get("id")
    if chat_id is None or telegram_id is None:
        await answer_callback(callback_id)
        return True

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(callback_id, text="Bạn cần /start trước nhé.")
        return True

    _, parts = parse_callback(data)
    action = parts[0] if parts else "start"
    arg = parts[1] if len(parts) > 1 else None

    # Run the ack and the action in parallel — see _dispatch_asset_action.
    await asyncio.gather(
        answer_callback(callback_id),
        _dispatch_asset_action(db, chat_id, user, action, arg),
    )
    return True  # consumed (any asset_add:* payload), even if no-op.


async def _mark_onboarding_first_asset_done(
    db: AsyncSession, user: User
) -> None:
    """Bridge for P3A-9 — see ``backend.bot.handlers.onboarding`` for usage.

    Imported lazily to avoid a circular import at module load.
    """
    from backend.bot.handlers import onboarding as onboarding_handlers
    await onboarding_handlers.note_first_asset_added_if_needed(db, user)
