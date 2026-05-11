"""Asset-entry wizard handler.

Five flows — cash, stock, crypto, gold, real-estate — share a common entry point
and dispatcher, plus a Phase 3.8 "mark existing as rental" flow. State
lives on ``users.wizard_state`` (JSONB) so the bot can survive process
restarts mid-wizard.

Flow names (stored in ``wizard_state.flow``):

    asset_add_cash         — 2 questions: subtype → "name + amount"
    asset_add_stock        — 4 questions: subtype → ticker → quantity
                             → avg_price → (same|new current_price)
    asset_add_crypto       — subtype → symbol → quantity → avg_price
                             → (same|new current_price)
    asset_add_gold         — subtype → quantity → avg_price
                             → (same|new current_price)
    asset_add_real_estate  — 4 questions + optional rental sub-wizard:
                             subtype → name → initial_value →
                             current_value → rental_ask (Y/N) →
                             [rental_rent → rental_expenses →
                              rental_status → rental_extra]
    asset_add_mark_rental  — Phase 3.8: pick existing real-estate
                             then run only the rental sub-wizard
                             (rental_rent → rental_expenses →
                              rental_status → rental_extra).

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
import contextlib
import html
import logging
import re
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.money import format_money_full, format_money_short
from backend.bot.formatters.wealth_formatter import (
    format_asset_added,
    format_asset_list,
    format_rental_marked,
)
from backend.bot.keyboards.asset_keyboard import (
    add_more_keyboard,
    asset_delete_confirm_keyboard,
    asset_delete_list_keyboard,
    asset_delete_type_keyboard,
    asset_dashboard_delete_confirm_keyboard,
    asset_dashboard_edit_keyboard,
    asset_edit_list_keyboard,
    asset_manage_keyboard,
    asset_market_manage_keyboard,
    asset_type_picker_keyboard,
    cash_subtype_keyboard,
    crypto_current_price_keyboard,
    crypto_subtype_keyboard,
    gold_current_price_keyboard,
    gold_subtype_keyboard,
    real_estate_subtype_keyboard,
    rental_ask_keyboard,
    rental_extra_keyboard,
    rental_pick_existing_keyboard,
    rental_status_keyboard,
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
from backend.wealth.asset_types import (
    AssetType,
    get_label,
    get_subtype_icon,
    get_subtypes,
)
from backend.wealth.fx import USD_VND_RATE, parse_usd_amount, usd_to_vnd
from backend.services.wealth_dashboard_service import (
    SORT_ALPHA,
    SORT_TYPE,
    SORT_VALUE_ASC,
    SORT_VALUE_DESC,
    normalize_sort,
)
from backend.wealth.ladder import update_user_level
from backend.wealth.schemas.rental import OccupancyStatus, RentalMetadata
from backend.wealth.services import asset_service, net_worth_calculator, rental_service

logger = logging.getLogger(__name__)

_DASHBOARD_SORT_BY_USER: dict[uuid.UUID, str] = {}


class AssetEvent:
    """Analytics event names for the asset-entry funnel."""

    WIZARD_OPENED = "asset_wizard_opened"
    TYPE_PICKED = "asset_wizard_type_picked"
    ASSET_ADDED = "asset_added"
    ASSET_UNDONE = "asset_undone"
    WIZARD_CANCELED = "asset_wizard_canceled"
    PARSE_FAILED = "asset_wizard_parse_failed"
    # Phase 3.8 Epic 1
    RENTAL_MARKED = "rental_marked"
    RENTAL_DECLINED = "rental_declined"
    RENTAL_FLOW_OPENED = "rental_flow_opened"


# Flow names persisted in wizard_state.
# All start with "asset_add" so the text dispatcher can detect "user is mid
# asset-wizard" with a single prefix check (see ``handle_asset_text_input``).
FLOW_PICKER = "asset_add_picker"  # 6-button type picker shown, nothing chosen
FLOW_CASH = "asset_add_cash"
FLOW_STOCK = "asset_add_stock"
FLOW_CRYPTO = "asset_add_crypto"
FLOW_GOLD = "asset_add_gold"
FLOW_REAL_ESTATE = "asset_add_real_estate"
# Phase 3.8 — "mark existing real-estate as rental" flow. Distinct from
# FLOW_REAL_ESTATE because it skips the create-asset path and only
# attaches rental data to an existing row.
FLOW_MARK_RENTAL = "asset_add_mark_rental"
# Phase 3.9.5 — launched from dashboard:edit:<asset_id>.
# Keep the asset_add prefix so existing wizard cancellation/auto-exit logic applies.
FLOW_EDIT_ASSET = "asset_add_edit_asset"


# ---------- Entry point ----------------------------------------------


async def start_asset_wizard(db: AsyncSession, chat_id: int, user: User) -> None:
    """Show the 6-button asset-type picker. First step of every flow.

    Sets ``wizard_state`` to a picker sentinel rather than clearing it, so
    that text typed while the picker (or a downstream subtype keyboard) is
    on screen gets caught by ``handle_asset_text_input`` and answered with
    a "tap a button" nudge — instead of falling through to the NL expense
    parser and being silently saved as a transaction.
    """
    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_PICKER,
        step="type",
        draft={},
    )
    await send_message(
        chat_id=chat_id,
        text=("💎 <b>Thêm tài sản mới</b>\n\nLoại tài sản nào bạn muốn thêm?"),
        parse_mode="HTML",
        reply_markup=asset_type_picker_keyboard(),
    )
    analytics.track(AssetEvent.WIZARD_OPENED, user_id=user.id)


async def cancel_wizard(db: AsyncSession, chat_id: int, user: User) -> bool:
    """Clear an active asset-wizard state and acknowledge.

    Returns True if there was an asset wizard to cancel. Used by the
    ``/huy`` and ``/cancel`` commands so the user has a text-based escape
    hatch in addition to the inline ❌ Hủy button. Covers both the
    standard add-asset flow and the Phase 3.8 mark-as-rental flow,
    since both share the ``asset_add_*`` prefix.
    """
    flow = (user.wizard_state or {}).get("flow") or ""
    if not flow.startswith("asset_add"):
        return False
    await wizard_service.clear(db, user.id)
    analytics.track(AssetEvent.WIZARD_CANCELED, user_id=user.id)
    await send_message(chat_id=chat_id, text="Đã huỷ. Quay lại lúc nào cũng được 👋")
    return True


async def list_assets(db: AsyncSession, chat_id: int, user: User) -> None:
    """Handle /taisan — display all active assets for the user."""
    assets = await asset_service.get_user_assets(db, user.id)
    await send_message(
        chat_id=chat_id,
        text=format_asset_list(_sort_assets_for_dashboard(assets, SORT_VALUE_DESC)),
        parse_mode="HTML",
    )


def _asset_dashboard_row_label(asset) -> str:
    icon = get_subtype_icon(asset.asset_type, asset.subtype)
    return f"{icon} {asset.name} — {format_money_short(asset.current_value)}"


def _asset_created_at_desc(asset) -> int:
    value = getattr(asset, "created_at", None)
    if value is None:
        return 0
    if hasattr(value, "timestamp"):
        return -int(value.timestamp())
    if hasattr(value, "toordinal"):
        return -int(value.toordinal())
    return 0


def _sort_assets_for_dashboard(assets: list, sort: str | None) -> list:
    sort_key = normalize_sort(sort)

    def name_key(asset) -> str:
        return str(getattr(asset, "name", "") or "").casefold()

    if sort_key == SORT_TYPE:
        return sorted(
            assets,
            key=lambda asset: (
                get_label(getattr(asset, "asset_type", "")).casefold(),
                name_key(asset),
                _asset_created_at_desc(asset),
            ),
        )
    if sort_key == SORT_VALUE_DESC:
        return sorted(
            assets,
            key=lambda asset: (
                Decimal(getattr(asset, "current_value", 0) or 0),
                name_key(asset),
                _asset_created_at_desc(asset),
            ),
            reverse=True,
        )
    if sort_key == SORT_VALUE_ASC:
        return sorted(
            assets,
            key=lambda asset: (
                Decimal(getattr(asset, "current_value", 0) or 0),
                name_key(asset),
                _asset_created_at_desc(asset),
            ),
        )
    return sorted(
        assets,
        key=lambda asset: (name_key(asset), _asset_created_at_desc(asset)),
    )


def _dashboard_sort_for_user(user: User) -> str:
    return normalize_sort(_DASHBOARD_SORT_BY_USER.get(user.id))


def _dashboard_sort_label(sort: str) -> str:
    return {
        SORT_VALUE_DESC: "Lớn → Nhỏ",
        SORT_VALUE_ASC: "Nhỏ → Lớn",
        SORT_TYPE: "Theo loại",
        SORT_ALPHA: "A-Z",
    }.get(normalize_sort(sort), "Lớn → Nhỏ")


async def show_asset_dashboard_report(
    db: AsyncSession,
    chat_id: int,
    user: User,
    *,
    sort: str | None = None,
    message_id: int | None = None,
) -> None:
    """Render the asset dashboard report with inline row actions."""
    sort_key = normalize_sort(sort or _dashboard_sort_for_user(user))
    _DASHBOARD_SORT_BY_USER[user.id] = sort_key
    assets = _sort_assets_for_dashboard(
        await asset_service.get_user_assets(db, user.id), sort_key
    )
    if not assets:
        text = (
            "📊 <b>Báo cáo</b>\n\n"
            "Bạn chưa có tài sản nào. Tap /themtaisan để bắt đầu nhé."
        )
        if message_id is not None:
            await edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML"
            )
        else:
            await send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        return

    rows = [(asset.id, _asset_dashboard_row_label(asset)) for asset in assets]
    text = (
        format_asset_list(assets).replace(
            "📊 <b>Tài sản của bạn</b>", "📊 <b>Báo cáo</b>", 1
        )
        + f"\n\nSắp xếp: <b>{html.escape(_dashboard_sort_label(sort_key))}</b>"
        + "\n👆 Dùng ✏️ để sửa, 🗑️ để xoá."
    )
    markup = asset_dashboard_edit_keyboard(rows, current_sort=sort_key)
    if message_id is not None:
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
    else:
        await send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )


async def show_asset_edit_picker(
    db: AsyncSession, chat_id: int, user: User, asset_id_texts: list[str]
) -> None:
    """Show concrete asset rows when a dashboard card represents a group."""
    requested_ids: set[uuid.UUID] = set()
    for raw in asset_id_texts[:20]:
        with contextlib.suppress(ValueError):
            requested_ids.add(uuid.UUID(str(raw)))

    if not requested_ids:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản này.")
        return

    # One ownership-scoped query is faster and avoids leaking whether ids
    # outside this user exist. Preserve dashboard order from ``asset_id_texts``.
    assets = await asset_service.get_user_assets(db, user.id)
    by_id = {asset.id: asset for asset in assets if asset.id in requested_ids}
    rows = []
    for raw in asset_id_texts[:20]:
        with contextlib.suppress(ValueError):
            asset = by_id.get(uuid.UUID(str(raw)))
            if asset is not None and asset.is_active:
                rows.append((asset.id, _asset_dashboard_row_label(asset)))

    if not rows:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản này.")
        return
    if len(rows) == 1:
        await start_asset_edit_wizard(db, chat_id, user, str(rows[0][0]))
        return

    await send_message(
        chat_id=chat_id,
        text="✏️ Card này gồm nhiều tài sản. Chọn dòng cụ thể để sửa nhé:",
        parse_mode="HTML",
        reply_markup=asset_dashboard_edit_keyboard(rows),
    )


async def start_asset_edit_wizard(
    db: AsyncSession,
    chat_id: int,
    user: User,
    asset_id_text: str,
    *,
    return_to_dashboard: bool = True,
    return_to_portfolio: str | None = None,
    dashboard_message_id: int | None = None,
) -> None:
    """Start the lightweight edit flow for one ownership-checked asset."""
    try:
        asset_uuid = uuid.UUID(asset_id_text)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản này.")
        return

    asset = await asset_service.get_asset_by_id(db, user.id, asset_uuid)
    if asset is None or not asset.is_active:
        await send_message(
            chat_id=chat_id, text="Tài sản này không còn trong danh sách."
        )
        return

    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_EDIT_ASSET,
        step="current_value",
        draft={
            "asset_id": str(asset.id),
            "asset_name": asset.name,
            "return_to_dashboard": return_to_dashboard,
            "return_to_portfolio": return_to_portfolio,
            "dashboard_message_id": dashboard_message_id,
        },
    )
    safe_name = html.escape(asset.name or "Tài sản")
    await send_message(
        chat_id=chat_id,
        text=(
            f"✏️ <b>Sửa {safe_name}</b>\n\n"
            f"Giá trị hiện tại: <b>{format_money_full(asset.current_value)}</b>\n"
            "Nhập giá trị mới nhé. Ví dụ: <code>120 triệu</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_edit_current_value_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Giá trị mới phải từ 0 trở lên nhé 🙂")
        return

    new_value = parse_amount(text)
    if new_value is None or new_value < 0:
        await send_message(
            chat_id=chat_id,
            text="Mình chưa đọc được số tiền. Ví dụ: <code>120 triệu</code>",
            parse_mode="HTML",
        )
        return

    try:
        asset_uuid = uuid.UUID(str(draft.get("asset_id") or ""))
    except ValueError:
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản này.")
        return

    asset = await asset_service.update_current_value(
        db, user.id, asset_uuid, Decimal(new_value)
    )
    breakdown = await net_worth_calculator.calculate_stored_current(db, user.id)
    await update_user_level(db, user.id, breakdown.total)
    await wizard_service.clear(db, user.id)

    from backend.miniapp.routes import invalidate_wealth_cache_for_user

    with contextlib.suppress(Exception):
        invalidate_wealth_cache_for_user(user.id)

    safe_name = html.escape(asset.name or "Tài sản")
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đã cập nhật <b>{safe_name}</b>: "
            f"<b>{format_money_full(asset.current_value)}</b>\n"
            f"💎 Tổng tài sản mới: <b>{format_money_full(breakdown.total)}</b>"
        ),
        parse_mode="HTML",
    )
    if draft.get("return_to_dashboard"):
        dashboard_message_id = draft.get("dashboard_message_id")
        if isinstance(dashboard_message_id, int):
            await show_asset_dashboard_report(
                db, chat_id, user, message_id=dashboard_message_id
            )
        else:
            await show_asset_dashboard_report(db, chat_id, user)
        return
    return_to_portfolio = draft.get("return_to_portfolio")
    if return_to_portfolio in {"stock", "crypto", "gold"}:
        await show_asset_market_portfolio_after_edit(
            db, chat_id, user, str(return_to_portfolio)
        )


async def show_asset_market_portfolio_after_edit(
    db: AsyncSession, chat_id: int, user: User, asset_type: str
) -> None:
    """Return to the filtered market portfolio after an edit flow."""
    from backend.intent.handlers.query_portfolio import QueryPortfolioHandler
    from backend.intent.intents import IntentResult, IntentType

    result = IntentResult(
        intent=IntentType.QUERY_PORTFOLIO,
        confidence=1.0,
        parameters={"asset_type": asset_type},
        raw_text=f"[market:{asset_type}:portfolio_after_edit]",
    )
    text = await QueryPortfolioHandler().handle(result, user, db)
    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=asset_market_manage_keyboard(asset_type),
    )


async def show_asset_manage_menu(db: AsyncSession, chat_id: int, user: User) -> None:
    """Open asset management actions from ``Tài sản → Sửa tài sản``."""
    await send_message(
        chat_id=chat_id,
        text=(
            "✏️ <b>Sửa tài sản</b>\n\nBạn muốn làm gì với danh mục tài sản hiện tại?"
        ),
        parse_mode="HTML",
        reply_markup=asset_manage_keyboard(),
    )


def _asset_delete_row_label(asset) -> str:
    icon = get_subtype_icon(asset.asset_type, asset.subtype)
    return f"{icon} {asset.name} — {format_money_short(asset.current_value)}"


async def show_asset_edit_list(
    db: AsyncSession, chat_id: int, user: User, asset_type: str
) -> None:
    """List only active assets of one type for quick market-context edits."""
    assets = _sort_assets_for_dashboard(
        await asset_service.get_user_assets(db, user.id, asset_type=asset_type),
        _dashboard_sort_for_user(user),
    )
    label = get_label(asset_type)
    if not assets:
        await send_message(
            chat_id=chat_id,
            text=(
                f"Chưa có tài sản loại này ({html.escape(label)}).\n\n"
                "Bạn có thể thêm tài sản đầu tiên để Bé Tiền theo dõi giúp nhé."
            ),
            parse_mode="HTML",
            reply_markup=asset_edit_list_keyboard([], asset_type=asset_type),
        )
        return

    candidates = [(asset.id, _asset_delete_row_label(asset)) for asset in assets]
    await send_message(
        chat_id=chat_id,
        text=f"Chọn tài sản <b>{html.escape(label)}</b> muốn sửa:",
        parse_mode="HTML",
        reply_markup=asset_edit_list_keyboard(candidates, asset_type=asset_type),
    )


async def show_asset_delete_type_picker(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Ask the user for an asset type before rendering delete rows."""
    await send_message(
        chat_id=chat_id,
        text=(
            "🗑 <b>Xoá tài sản</b>\n\n"
            "Chọn loại tài sản trước để danh sách gọn và tránh xoá nhầm nhé."
        ),
        parse_mode="HTML",
        reply_markup=asset_delete_type_keyboard(),
    )


async def show_asset_delete_list(
    db: AsyncSession, chat_id: int, user: User, asset_type: str
) -> None:
    """List only active assets of one type for deletion."""
    assets = _sort_assets_for_dashboard(
        await asset_service.get_user_assets(db, user.id, asset_type=asset_type),
        _dashboard_sort_for_user(user),
    )
    label = get_label(asset_type)
    if not assets:
        await send_message(
            chat_id=chat_id,
            text=f"Không có tài sản loại {label}.",
            parse_mode="HTML",
            reply_markup=asset_delete_type_keyboard(),
        )
        return

    candidates = [(asset.id, _asset_delete_row_label(asset)) for asset in assets]
    await send_message(
        chat_id=chat_id,
        text=f"Chọn tài sản <b>{label}</b> muốn xoá:",
        parse_mode="HTML",
        reply_markup=asset_delete_list_keyboard(candidates, asset_type=asset_type),
    )


async def _confirm_asset_delete(
    db: AsyncSession, chat_id: int, user: User, asset_id_text: str
) -> None:
    try:
        asset_uuid = uuid.UUID(asset_id_text)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản này.")
        return

    asset = await asset_service.get_asset_by_id(db, user.id, asset_uuid)
    if asset is None or not asset.is_active:
        await _send_asset_already_gone(db, chat_id, user, asset)
        return

    rental_warning = (
        "\n• Dòng tiền thuê hàng tháng sẽ ngừng tính." if asset.is_rental else ""
    )
    await send_message(
        chat_id=chat_id,
        text=(
            "🗑 <b>Xác nhận xoá tài sản</b>\n\n"
            f"{_asset_delete_row_label(asset)}\n\n"
            "Sau khi xoá:\n"
            "• Tài sản biến mất khỏi danh mục.\n"
            "• Tổng tài sản và dòng tiền tự động tính lại."
            f"{rental_warning}"
        ),
        parse_mode="HTML",
        reply_markup=asset_delete_confirm_keyboard(
            asset.id, asset_type=asset.asset_type
        ),
    )


async def _soft_delete_asset(
    db: AsyncSession, chat_id: int, user: User, asset_id_text: str
) -> None:
    try:
        asset_uuid = uuid.UUID(asset_id_text)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản này.")
        return

    asset = await asset_service.get_asset_by_id(db, user.id, asset_uuid)
    if asset is None or not asset.is_active:
        await _send_asset_already_gone(db, chat_id, user, asset)
        return

    asset_name = asset.name
    asset_type = asset.asset_type
    was_rental = bool(asset.is_rental)

    await asset_service.soft_delete(db, user.id, asset_uuid)
    # Pause linked rental income stream (no-op for non-rental assets) so
    # the cash-flow forecaster stops crediting rent from a deleted home.
    rental_paused = await rental_service.pause_streams_for_asset(
        db, user.id, asset_uuid
    )
    breakdown = await net_worth_calculator.calculate_stored_current(db, user.id)
    await update_user_level(db, user.id, breakdown.total)

    rental_note = (
        "\n🏠 Dòng thuê hàng tháng đã tạm dừng." if was_rental and rental_paused else ""
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đã xoá <b>{html.escape(asset_name)}</b> khỏi danh mục.\n"
            f"💎 Tổng tài sản: <b>{format_money_full(breakdown.total)}</b>\n"
            "💰 Dòng tiền sẽ được cập nhật ở lần xem tiếp theo."
            f"{rental_note}"
        ),
        parse_mode="HTML",
    )
    # Re-render the (now-fresh) delete list so the user sees the
    # updated state in-place — avoids the stale-list confusion where
    # the previous "Chọn tài sản muốn xoá" message still shows the
    # row they just removed.
    await show_asset_delete_list(db, chat_id, user, asset_type)


async def _confirm_dashboard_asset_delete(
    db: AsyncSession,
    chat_id: int,
    message_id: int | None,
    user: User,
    asset_id_text: str,
) -> None:
    try:
        asset_uuid = uuid.UUID(asset_id_text)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản này.")
        return

    asset = await asset_service.get_asset_by_id(db, user.id, asset_uuid)
    if asset is None or not asset.is_active:
        await _send_asset_already_gone(db, chat_id, user, asset)
        return

    sort_key = _dashboard_sort_for_user(user)
    rental_warning = (
        "\n• Dòng tiền thuê hàng tháng sẽ ngừng tính." if asset.is_rental else ""
    )
    text = (
        "🗑 <b>Xác nhận xoá tài sản</b>\n\n"
        f"{_asset_delete_row_label(asset)}\n\n"
        "Sau khi xoá:\n"
        "• Tài sản biến mất khỏi danh mục.\n"
        "• Tổng tài sản và dòng tiền tự động tính lại."
        f"{rental_warning}"
    )
    markup = asset_dashboard_delete_confirm_keyboard(asset.id, current_sort=sort_key)
    if message_id is not None:
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
    else:
        await send_message(
            chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=markup
        )


async def _soft_delete_dashboard_asset(
    db: AsyncSession,
    chat_id: int,
    message_id: int | None,
    user: User,
    asset_id_text: str,
) -> None:
    try:
        asset_uuid = uuid.UUID(asset_id_text)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy tài sản này.")
        return

    asset = await asset_service.get_asset_by_id(db, user.id, asset_uuid)
    if asset is None or not asset.is_active:
        await _send_asset_already_gone(db, chat_id, user, asset)
        return

    was_rental = bool(asset.is_rental)
    await asset_service.soft_delete(db, user.id, asset_uuid)
    rental_paused = await rental_service.pause_streams_for_asset(
        db, user.id, asset_uuid
    )
    breakdown = await net_worth_calculator.calculate_stored_current(db, user.id)
    await update_user_level(db, user.id, breakdown.total)

    from backend.miniapp.routes import invalidate_wealth_cache_for_user

    with contextlib.suppress(Exception):
        invalidate_wealth_cache_for_user(user.id)

    await show_asset_dashboard_report(
        db,
        chat_id,
        user,
        sort=_dashboard_sort_for_user(user),
        message_id=message_id,
    )


async def _send_asset_already_gone(
    db: AsyncSession,
    chat_id: int,
    user: User,
    asset: "object | None",  # Asset | None — quoted to avoid forward-ref churn
) -> None:
    """Friendly recovery when the user taps a button for an already-deleted
    or unknown asset (typically a stale list message). Re-renders a fresh
    list when we know the asset_type, otherwise sends the type picker.
    """
    asset_type = getattr(asset, "asset_type", None)
    await send_message(
        chat_id=chat_id,
        text="Tài sản này không còn trong danh sách. Đây là danh sách mới nhất 👇",
    )
    if asset_type:
        await show_asset_delete_list(db, chat_id, user, asset_type)
    else:
        await show_asset_delete_type_picker(db, chat_id, user)


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


async def _start_cash_subtype_pick(db: AsyncSession, chat_id: int, user: User) -> None:
    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_CASH,
        step="subtype",
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
        db,
        user.id,
        step="amount",
        draft_patch={"subtype": subtype},
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
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
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
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
        return

    name = label or {
        "bank_savings": "Tài khoản tiết kiệm",
        "bank_checking": "Tài khoản thanh toán",
        "cash": "Tiền mặt",
        "e_wallet": "Ví điện tử",
    }.get(draft.get("subtype", ""), "Tài khoản")

    asset = await asset_service.create_asset(
        db,
        user.id,
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


async def _start_stock_subtype_pick(db: AsyncSession, chat_id: int, user: User) -> None:
    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_STOCK,
        step="subtype",
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
        db,
        user.id,
        step="ticker",
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
        text=(f"📈 <b>Mã (ticker) là gì?</b>\n\nVí dụ: {examples}"),
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
        db,
        user.id,
        step="quantity",
        draft_patch={"extra": extra, "name": ticker},
    )
    unit = _stock_unit_label(draft.get("subtype"))
    await send_message(
        chat_id=chat_id,
        text=(f"✅ <b>{ticker}</b>\n\nBạn đang sở hữu bao nhiêu {unit}?"),
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
        db,
        user.id,
        step="avg_price",
        draft_patch={"extra": extra},
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
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
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
        analytics.track(
            AssetEvent.PARSE_FAILED,
            user_id=user.id,
            properties={"flow": FLOW_STOCK, "field": "avg_price"},
        )
        example = (
            "Ví dụ: <code>150</code> hoặc <code>150.5</code> (USD)"
            if is_foreign
            else "Ví dụ: <code>45000</code> hoặc <code>45k</code>"
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
        db,
        user.id,
        step="current_price",
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
                f"💹 Nhập giá hiện tại của 1 {unit} (USD):\nVí dụ: <code>165</code>"
            )
        elif subtype == "fund":
            prompt = f"💹 Nhập giá hiện tại của 1 {unit}:\nVí dụ: <code>16000</code>"
        else:
            prompt = f"💹 Nhập giá hiện tại của 1 {unit}:\nVí dụ: <code>52000</code>"
        await send_message(chat_id=chat_id, text=prompt, parse_mode="HTML")


async def _handle_stock_current_price_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
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
            "Ví dụ: <code>165</code> (USD)"
            if is_foreign
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
        current_price_usd = Decimal(
            str(
                extra.get("current_price_usd")
                if extra.get("current_price_usd") is not None
                else extra.get("avg_price_usd") or 0
            )
        )
        extra["current_price_usd"] = float(current_price_usd)
        extra["initial_value_usd"] = float(avg_price_usd * quantity)
        extra["current_value_usd"] = float(current_price_usd * quantity)
        extra["current_price"] = float(current_price)

    asset = await asset_service.create_asset(
        db,
        user.id,
        asset_type=AssetType.STOCK.value,
        subtype=draft.get("subtype"),
        name=name,
        initial_value=initial_value,
        current_value=current_value,
        extra=extra,
    )
    await _post_save(db, chat_id, user, asset)


# ---------- Crypto flow -----------------------------------------------

_CRYPTO_DEFAULT_SYMBOLS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
}


def _parse_positive_decimal(text: str) -> Decimal | None:
    cleaned = text.strip().replace(" ", "")
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        value = Decimal(cleaned)
    except Exception:
        return None
    return value if value > 0 else None


async def _start_crypto_subtype_pick(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_CRYPTO,
        step="subtype",
        draft={"asset_type": AssetType.CRYPTO.value, "extra": {}},
    )
    await send_message(
        chat_id=chat_id,
        text="₿ Loại tiền số nào?",
        parse_mode="HTML",
        reply_markup=crypto_subtype_keyboard(),
    )


async def _handle_crypto_subtype_pick(
    db: AsyncSession, chat_id: int, user: User, subtype: str
) -> None:
    subs = get_subtypes(AssetType.CRYPTO.value)
    if subtype not in subs:
        await send_message(chat_id=chat_id, text="Loại không hợp lệ.")
        return

    symbol = _CRYPTO_DEFAULT_SYMBOLS.get(subtype)
    if symbol:
        extra = {"symbol": symbol, "ticker": symbol}
        await wizard_service.update_step(
            db,
            user.id,
            step="quantity",
            draft_patch={"subtype": subtype, "name": symbol, "extra": extra},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>{symbol}</b>\n\n"
                "Bạn đang sở hữu bao nhiêu coin?\n"
                "Ví dụ: <code>0.05</code>"
            ),
            parse_mode="HTML",
        )
        return

    examples = (
        "<code>USDT</code>, <code>USDC</code>"
        if subtype == "stablecoin"
        else "<code>SOL</code>, <code>BNB</code>"
    )
    await wizard_service.update_step(
        db,
        user.id,
        step="symbol",
        draft_patch={"subtype": subtype, "extra": {}},
    )
    await send_message(
        chat_id=chat_id,
        text=f"🪙 <b>Mã coin là gì?</b>\n\nVí dụ: {examples}",
        parse_mode="HTML",
    )


async def _handle_crypto_symbol_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    symbol = text.strip().split()[0].upper() if text.strip() else ""
    if not symbol.isalnum() or len(symbol) > 12:
        await send_message(
            chat_id=chat_id,
            text="Mã coin chưa hợp lệ. Ví dụ: BTC, ETH, SOL.",
        )
        return

    extra = dict(draft.get("extra") or {})
    extra["symbol"] = symbol
    extra["ticker"] = symbol
    await wizard_service.update_step(
        db,
        user.id,
        step="quantity",
        draft_patch={"extra": extra, "name": symbol},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>{symbol}</b>\n\n"
            "Bạn đang sở hữu bao nhiêu coin?\n"
            "Ví dụ: <code>0.05</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_crypto_quantity_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số lượng phải lớn hơn 0 nhé 🙂")
        return
    quantity = _parse_positive_decimal(text)
    if quantity is None:
        await send_message(
            chat_id=chat_id,
            text="Nhập số lượng coin nhé. Ví dụ: <code>0.05</code>",
            parse_mode="HTML",
        )
        return

    extra = dict(draft.get("extra") or {})
    extra["quantity"] = float(quantity)
    await wizard_service.update_step(
        db,
        user.id,
        step="avg_price",
        draft_patch={"extra": extra},
    )
    symbol = extra.get("symbol", "coin")
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>{quantity}</b> {symbol}\n\n"
            "Giá mua trung bình mỗi coin là bao nhiêu (VNĐ)?\n"
            "Ví dụ: <code>2 tỷ</code>, <code>1500tr</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_crypto_avg_price_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
        return
    avg_price = parse_amount(text)
    if avg_price is None or avg_price <= 0:
        await send_message(
            chat_id=chat_id,
            text="Nhập giá giúp mình nhé. Ví dụ: <code>2 tỷ</code>",
            parse_mode="HTML",
        )
        return

    extra = dict(draft.get("extra") or {})
    extra["avg_price"] = float(avg_price)
    quantity = Decimal(str(extra.get("quantity") or 0))
    initial_value = avg_price * quantity
    await wizard_service.update_step(
        db,
        user.id,
        step="current_price",
        draft_patch={"extra": extra, "initial_value": float(initial_value)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Tổng vốn: <b>{int(initial_value):,}đ</b>\n\n"
            "Giá hiện tại của 1 coin là bao nhiêu?\n"
            "(Hoặc dùng giá mua nếu không nhớ)"
        ),
        parse_mode="HTML",
        reply_markup=crypto_current_price_keyboard(),
    )


async def _handle_crypto_current_price_choice(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict
) -> None:
    if choice == "same":
        avg_price = Decimal(str(draft.get("extra", {}).get("avg_price") or 0))
        await _save_crypto_asset(db, chat_id, user, draft, avg_price)
    elif choice == "new":
        await wizard_service.update_step(db, user.id, step="current_price_input")
        await send_message(
            chat_id=chat_id,
            text=("💹 Nhập giá hiện tại của 1 coin (VNĐ):\nVí dụ: <code>2.2 tỷ</code>"),
            parse_mode="HTML",
        )


async def _handle_crypto_current_price_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
        return
    current_price = parse_amount(text)
    if current_price is None or current_price <= 0:
        await send_message(
            chat_id=chat_id,
            text="Nhập giá giúp mình nhé. Ví dụ: <code>2.2 tỷ</code>",
            parse_mode="HTML",
        )
        return
    await _save_crypto_asset(db, chat_id, user, draft, current_price)


async def _save_crypto_asset(
    db: AsyncSession, chat_id: int, user: User, draft: dict, current_price: Decimal
) -> None:
    extra = dict(draft.get("extra") or {})
    quantity = Decimal(str(extra.get("quantity") or 0))
    avg_price = Decimal(str(extra.get("avg_price") or 0))
    initial_value = avg_price * quantity
    current_value = current_price * quantity
    extra["current_price"] = float(current_price)
    name = draft.get("name") or extra.get("symbol") or "Crypto"

    asset = await asset_service.create_asset(
        db,
        user.id,
        asset_type=AssetType.CRYPTO.value,
        subtype=draft.get("subtype"),
        name=name,
        initial_value=initial_value,
        current_value=current_value,
        extra=extra,
    )
    await _post_save(db, chat_id, user, asset)


# ---------- Gold flow --------------------------------------------------

_GOLD_TYPE_BY_SUBTYPE: dict[str, str] = {
    "sjc": "SJC",
    "pnj": "PNJ",
    "nhan": "NHAN_24K",
    "trang_suc": "JEWELRY",
}
_GOLD_SYMBOL_BY_SUBTYPE: dict[str, str] = {
    "sjc": "SJC_GOLD",
    "pnj": "SJC_GOLD",
    "nhan": "RING_24K",
    "trang_suc": "SJC_GOLD",
}
_GOLD_QUANTITY_RE = re.compile(r"(?P<num>\d+(?:[.,]\d+)?)")
_GOLD_GRAM_RE = re.compile(r"(?<![a-z])(?:gram|grams|gam|g)\b")


def _parse_gold_quantity(text: str) -> tuple[Decimal, Decimal] | None:
    """Parse a Vietnamese gold quantity into (lượng, grams).

    Defaults to lượng when the user only types a number. Also accepts
    chỉ/phân/gram because users commonly describe small gold holdings
    with those units.
    """
    match = _GOLD_QUANTITY_RE.search((text or "").strip().lower())
    if match is None:
        return None
    amount = Decimal(match.group("num").replace(",", "."))
    if amount <= 0:
        return None

    lowered = text.lower()
    if _GOLD_GRAM_RE.search(lowered):
        grams = amount
        tael = grams / Decimal("37.5")
    elif "chỉ" in lowered or "chi" in lowered:
        tael = amount / Decimal(10)
        grams = amount * Decimal("3.75")
    elif "phân" in lowered or "phan" in lowered:
        tael = amount / Decimal(100)
        grams = amount * Decimal("0.375")
    else:
        tael = amount
        grams = amount * Decimal("37.5")
    return tael, grams


async def _start_gold_subtype_pick(db: AsyncSession, chat_id: int, user: User) -> None:
    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_GOLD,
        step="subtype",
        draft={"asset_type": AssetType.GOLD.value, "extra": {}},
    )
    await send_message(
        chat_id=chat_id,
        text="🥇 Bạn muốn thêm loại vàng nào?",
        parse_mode="HTML",
        reply_markup=gold_subtype_keyboard(),
    )


async def _handle_gold_subtype_pick(
    db: AsyncSession, chat_id: int, user: User, subtype: str
) -> None:
    subs = get_subtypes(AssetType.GOLD.value)
    if subtype not in subs:
        await send_message(chat_id=chat_id, text="Loại không hợp lệ.")
        return

    extra = {
        "type": _GOLD_TYPE_BY_SUBTYPE.get(subtype, subtype.upper()),
        "symbol": _GOLD_SYMBOL_BY_SUBTYPE.get(subtype, "SJC_GOLD"),
    }
    await wizard_service.update_step(
        db,
        user.id,
        step="quantity",
        draft_patch={"subtype": subtype, "name": subs[subtype], "extra": extra},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"⚖️ Bạn đang có bao nhiêu <b>{subs[subtype]}</b>?\n\n"
            "Ví dụ: <code>2 lượng</code>, <code>5 chỉ</code>, "
            "hoặc <code>37.5 gram</code>."
        ),
        parse_mode="HTML",
    )


async def _handle_gold_quantity_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số lượng vàng phải lớn hơn 0 nhé 🙂")
        return
    parsed = _parse_gold_quantity(text)
    if parsed is None:
        await send_message(
            chat_id=chat_id,
            text="Nhập số lượng vàng nhé. Ví dụ: <code>2 lượng</code> hoặc <code>5 chỉ</code>",
            parse_mode="HTML",
        )
        return

    tael, grams = parsed
    extra = dict(draft.get("extra") or {})
    extra["quantity"] = float(tael)
    extra["tael"] = float(tael)
    extra["weight_gram"] = float(grams)
    await wizard_service.update_step(
        db,
        user.id,
        step="avg_price",
        draft_patch={"extra": extra},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>{tael.normalize()}</b> lượng (~{grams.normalize()}g)\n\n"
            "Giá mua trung bình mỗi lượng là bao nhiêu (VNĐ)?\n"
            "Ví dụ: <code>90 triệu</code>, <code>92tr</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_gold_avg_price_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
        return
    avg_price = parse_amount(text)
    if avg_price is None or avg_price <= 0:
        await send_message(
            chat_id=chat_id,
            text="Nhập giá mua mỗi lượng nhé. Ví dụ: <code>90 triệu</code>",
            parse_mode="HTML",
        )
        return

    extra = dict(draft.get("extra") or {})
    extra["avg_price"] = float(avg_price)
    quantity = Decimal(str(extra.get("quantity") or 0))
    initial_value = avg_price * quantity
    await wizard_service.update_step(
        db,
        user.id,
        step="current_price",
        draft_patch={"extra": extra, "initial_value": float(initial_value)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Tổng vốn: <b>{int(initial_value):,}đ</b>\n\n"
            "Giá hiện tại của 1 lượng là bao nhiêu?\n"
            "(Hoặc dùng giá mua nếu chưa muốn cập nhật)"
        ),
        parse_mode="HTML",
        reply_markup=gold_current_price_keyboard(),
    )


async def _handle_gold_current_price_choice(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict
) -> None:
    if choice == "same":
        avg_price = Decimal(str(draft.get("extra", {}).get("avg_price") or 0))
        await _save_gold_asset(db, chat_id, user, draft, avg_price)
    elif choice == "new":
        await wizard_service.update_step(db, user.id, step="current_price_input")
        await send_message(
            chat_id=chat_id,
            text=(
                "💹 Nhập giá hiện tại của 1 lượng vàng (VNĐ):\n"
                "Ví dụ: <code>92 triệu</code>"
            ),
            parse_mode="HTML",
        )


async def _handle_gold_current_price_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
        return
    current_price = parse_amount(text)
    if current_price is None or current_price <= 0:
        await send_message(
            chat_id=chat_id,
            text="Nhập giá hiện tại mỗi lượng nhé. Ví dụ: <code>92 triệu</code>",
            parse_mode="HTML",
        )
        return
    await _save_gold_asset(db, chat_id, user, draft, current_price)


async def _save_gold_asset(
    db: AsyncSession, chat_id: int, user: User, draft: dict, current_price: Decimal
) -> None:
    extra = dict(draft.get("extra") or {})
    quantity = Decimal(str(extra.get("quantity") or extra.get("tael") or 0))
    avg_price = Decimal(str(extra.get("avg_price") or 0))
    initial_value = avg_price * quantity
    current_value = current_price * quantity
    extra["current_price"] = float(current_price)

    asset = await asset_service.create_asset(
        db,
        user.id,
        asset_type=AssetType.GOLD.value,
        subtype=draft.get("subtype"),
        name=draft.get("name") or "Vàng",
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
        db,
        user.id,
        FLOW_REAL_ESTATE,
        step="subtype",
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
        db,
        user.id,
        step="name",
        draft_patch={"subtype": subtype},
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
        # Phase 3.8: rental tracking is live. Nudge the user that
        # they'll get the rental Y/N step at the end of this wizard.
        await send_message(
            chat_id=chat_id,
            text=(
                "💡 Cuối wizard mình sẽ hỏi đây có phải BĐS cho thuê — "
                "bấm 'Có' để track tiền thuê + yield nhé."
            ),
        )

    await wizard_service.update_step(
        db,
        user.id,
        step="initial_value",
        draft_patch={"name": name},
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
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
        return
    amount = parse_amount(text)
    if amount is None or amount <= 0:
        analytics.track(
            AssetEvent.PARSE_FAILED,
            user_id=user.id,
            properties={"flow": FLOW_REAL_ESTATE, "field": "initial_value"},
        )
        await send_message(
            chat_id=chat_id,
            text="Nhập giá giúp mình. Ví dụ: <code>2 tỷ</code>",
            parse_mode="HTML",
        )
        return

    await wizard_service.update_step(
        db,
        user.id,
        step="current_value",
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
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
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

    # Persist current_value/initial_value into the draft and advance to
    # the rental Y/N question. We save the asset only after the user
    # answers, so the wizard can attach rental_metadata in one
    # transaction rather than create → mutate. This also makes "❌ Hủy"
    # at the rental step a clean abort: no orphan asset rows.
    await wizard_service.update_step(
        db,
        user.id,
        step="rental_ask",
        draft_patch={
            "initial_value": float(initial),
            "current_value": float(current),
        },
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Giá hiện tại: <b>{int(current):,}đ</b>\n\n"
            "🏠 <b>Đây có phải là BĐS cho thuê không?</b>"
        ),
        parse_mode="HTML",
        reply_markup=rental_ask_keyboard(),
    )


async def _save_real_estate_no_rental(
    db: AsyncSession, chat_id: int, user: User, draft: dict
) -> None:
    """Save the real-estate asset without rental data — the "no" branch
    of the rental Y/N prompt and also the path used when the rental
    sub-wizard is not entered."""
    initial = Decimal(str(draft.get("initial_value") or 0))
    current = Decimal(str(draft.get("current_value") or 0))
    if current <= 0:
        # Defensive — should never happen because the previous step
        # validates current_value, but if state got corrupted (e.g.
        # process restart mid-flow on stale draft) abort cleanly
        # instead of crashing.
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id,
            text="Có lỗi với wizard. Thử lại bằng /assets nhé.",
        )
        return
    if initial <= 0:
        initial = current

    extra = dict(draft.get("extra") or {})
    asset = await asset_service.create_asset(
        db,
        user.id,
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
            "💡 Bạn có thể update giá trị BĐS bất cứ lúc nào khi thị trường biến động."
        ),
    )
    await _post_save(db, chat_id, user, asset)


# ---------- Rental sub-wizard ---------------------------------------
#
# Re-used by two entry points:
#   1. FLOW_REAL_ESTATE — appended after the current_value step. The
#      asset is created at the end of the rental flow with rental
#      metadata attached in the same transaction.
#   2. FLOW_MARK_RENTAL — entered from the menu "Đánh dấu BĐS cho
#      thuê" action. The asset already exists; the rental flow only
#      attaches rental metadata to it.
#
# Step names are identical across both flows so the dispatcher can
# share text-input handlers; the only divergence is in the final
# "save" step which checks ``draft.mode``.


async def _handle_rental_ask_choice(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict
) -> None:
    """User answered the "Is this a rental?" yes/no prompt."""
    if choice == "no":
        analytics.track(AssetEvent.RENTAL_DECLINED, user_id=user.id)
        await _save_real_estate_no_rental(db, chat_id, user, draft)
        return

    if choice == "yes":
        analytics.track(AssetEvent.RENTAL_FLOW_OPENED, user_id=user.id)
        await wizard_service.update_step(
            db,
            user.id,
            step="rental_rent",
            draft_patch={"rental": {}},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "💰 <b>Tiền thuê hàng tháng?</b>\n\n"
                "Ví dụ: <code>15tr</code>, <code>15 triệu</code>"
            ),
            parse_mode="HTML",
        )


async def _handle_rental_rent_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂")
        return
    rent = parse_amount(text)
    if rent is None or rent <= 0:
        analytics.track(
            AssetEvent.PARSE_FAILED,
            user_id=user.id,
            properties={"flow": "rental", "field": "monthly_rent"},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "Mình chưa hiểu số tiền 😅\n"
                "Ví dụ: <code>15tr</code> hoặc <code>15000000</code>"
            ),
            parse_mode="HTML",
        )
        return

    rental = dict(draft.get("rental") or {})
    rental["monthly_rent"] = float(rent)
    await wizard_service.update_step(
        db,
        user.id,
        step="rental_expenses",
        draft_patch={"rental": rental},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Tiền thuê: <b>{int(rent):,}đ</b>/tháng\n\n"
            "🛠️ <b>Chi phí hàng tháng</b> (thuế, sửa chữa, môi giới)?\n\n"
            "Gửi <code>0</code> nếu không có."
        ),
        parse_mode="HTML",
    )


async def _handle_rental_expenses_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Chi phí phải ≥ 0 nhé 🙂")
        return
    cleaned = text.strip().lower()
    if cleaned in ("0", "không", "khong", "ko", "no"):
        expenses = Decimal(0)
    else:
        parsed = parse_amount(text)
        if parsed is None or parsed < 0:
            await send_message(
                chat_id=chat_id,
                text="Mình chưa hiểu. Ví dụ: <code>1.5tr</code> hoặc <code>0</code>",
                parse_mode="HTML",
            )
            return
        expenses = parsed

    rental = dict(draft.get("rental") or {})
    monthly_rent = Decimal(str(rental.get("monthly_rent") or 0))
    if expenses >= monthly_rent and monthly_rent > 0:
        # Soft warning — see RentalMetadata._check_expenses_not_silly.
        # Don't block; the user might intentionally be running a
        # loss-making rental during renovation. But surface it loudly
        # so a typo (15tr expenses vs 1.5tr) gets caught.
        await send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ Chi phí ({int(expenses):,}đ) ≥ tiền thuê "
                f"({int(monthly_rent):,}đ) — bạn nhập đúng chứ?\n\n"
                "Nếu typo, gõ lại số. Nếu đúng, bấm trạng thái phía dưới."
            ),
        )
    rental["monthly_expenses"] = float(expenses)
    await wizard_service.update_step(
        db,
        user.id,
        step="rental_status",
        draft_patch={"rental": rental},
    )
    await send_message(
        chat_id=chat_id,
        text="📍 <b>Trạng thái hiện tại?</b>",
        parse_mode="HTML",
        reply_markup=rental_status_keyboard(),
    )


async def _handle_rental_status_choice(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict
) -> None:
    if choice not in (OccupancyStatus.RENTED.value, OccupancyStatus.VACANT.value):
        await send_message(chat_id=chat_id, text="Trạng thái không hợp lệ.")
        return

    rental = dict(draft.get("rental") or {})
    rental["occupancy_status"] = choice
    if choice == OccupancyStatus.VACANT.value:
        # Vacant → no tenant info to collect, save immediately.
        await wizard_service.update_step(
            db,
            user.id,
            step="rental_save",
            draft_patch={"rental": rental},
        )
        await _commit_rental(db, chat_id, user, draft={**draft, "rental": rental})
        return

    # Rented → offer tenant / lease extras.
    await wizard_service.update_step(
        db,
        user.id,
        step="rental_extra",
        draft_patch={"rental": rental},
    )
    await send_message(
        chat_id=chat_id,
        text="Bạn muốn ghi thêm thông tin gì không?",
        reply_markup=rental_extra_keyboard(),
    )


async def _handle_rental_extra_choice(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict
) -> None:
    if choice in ("skip", "done"):
        await _commit_rental(db, chat_id, user, draft=draft)
        return

    if choice == "tenant":
        await wizard_service.update_step(db, user.id, step="rental_tenant_input")
        await send_message(
            chat_id=chat_id,
            text=("👤 <b>Tên người thuê?</b>\n\nGõ <code>skip</code> để bỏ qua."),
            parse_mode="HTML",
        )
        return

    if choice == "lease":
        await wizard_service.update_step(db, user.id, step="rental_lease_input")
        await send_message(
            chat_id=chat_id,
            text=(
                "📅 <b>Thời hạn hợp đồng thuê?</b>\n\n"
                "Format: <code>YYYY-MM-DD YYYY-MM-DD</code> "
                "(ngày bắt đầu - ngày kết thúc)\n"
                "Ví dụ: <code>2024-01-01 2025-12-31</code>\n\n"
                "Gõ <code>skip</code> để bỏ qua."
            ),
            parse_mode="HTML",
        )
        return


async def _handle_rental_tenant_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    cleaned = text.strip()
    if cleaned.lower() in ("skip", "bỏ qua", "bo qua"):
        rental = dict(draft.get("rental") or {})
    else:
        if len(cleaned) > 200:
            await send_message(chat_id=chat_id, text="Tên người thuê tối đa 200 ký tự.")
            return
        rental = dict(draft.get("rental") or {})
        rental["tenant_name"] = cleaned

    await wizard_service.update_step(
        db,
        user.id,
        step="rental_extra",
        draft_patch={"rental": rental},
    )
    await send_message(
        chat_id=chat_id,
        text="✅ Đã ghi nhận. Còn thông tin nào khác không?",
        reply_markup=rental_extra_keyboard(),
    )


async def _handle_rental_lease_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict
) -> None:
    cleaned = text.strip()
    if cleaned.lower() in ("skip", "bỏ qua", "bo qua"):
        rental = dict(draft.get("rental") or {})
        await wizard_service.update_step(
            db,
            user.id,
            step="rental_extra",
            draft_patch={"rental": rental},
        )
        await send_message(
            chat_id=chat_id,
            text="OK, bỏ qua nhé. Còn thông tin nào khác không?",
            reply_markup=rental_extra_keyboard(),
        )
        return

    parts = cleaned.split()
    if len(parts) != 2:
        await send_message(
            chat_id=chat_id,
            text=(
                "Format: <code>YYYY-MM-DD YYYY-MM-DD</code>\n"
                "Ví dụ: <code>2024-01-01 2025-12-31</code>"
            ),
            parse_mode="HTML",
        )
        return
    try:
        start = date.fromisoformat(parts[0])
        end = date.fromisoformat(parts[1])
    except ValueError:
        await send_message(
            chat_id=chat_id,
            text="Ngày không hợp lệ. Format: <code>YYYY-MM-DD YYYY-MM-DD</code>",
            parse_mode="HTML",
        )
        return
    if end <= start:
        await send_message(
            chat_id=chat_id,
            text="Ngày kết thúc phải sau ngày bắt đầu. Thử lại nhé.",
        )
        return

    rental = dict(draft.get("rental") or {})
    rental["lease_start_date"] = start.isoformat()
    rental["lease_end_date"] = end.isoformat()
    await wizard_service.update_step(
        db,
        user.id,
        step="rental_extra",
        draft_patch={"rental": rental},
    )
    await send_message(
        chat_id=chat_id,
        text=f"✅ Đã ghi: <b>{start} → {end}</b>. Còn thông tin nào khác không?",
        parse_mode="HTML",
        reply_markup=rental_extra_keyboard(),
    )


async def _commit_rental(
    db: AsyncSession,
    chat_id: int,
    user: User,
    draft: dict,
) -> None:
    """Final step: validate metadata, save asset (or mark existing),
    create/refresh income stream, send confirmation."""
    rental = dict(draft.get("rental") or {})
    try:
        # Pydantic re-validates everything (rent > 0, expenses ≥ 0,
        # lease dates ordered) so a corrupted draft can't reach the DB.
        metadata = RentalMetadata.model_validate(rental)
    except Exception as exc:
        logger.warning("rental metadata validation failed: %s", exc)
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id,
            text="Dữ liệu chưa hợp lệ — bạn thử lại từ /menu nhé.",
        )
        return

    mode = draft.get("mode")
    if mode == "mark_existing":
        # FLOW_MARK_RENTAL: asset already exists; just attach metadata.
        asset_id_str = draft.get("target_asset_id")
        try:
            asset_id = uuid.UUID(str(asset_id_str))
        except (TypeError, ValueError):
            await wizard_service.clear(db, user.id)
            await send_message(
                chat_id=chat_id,
                text="Không tìm thấy BĐS đích.",
            )
            return
        try:
            asset = await rental_service.mark_as_rental(
                db,
                user.id,
                asset_id,
                metadata,
            )
        except ValueError as exc:
            logger.warning("mark_as_rental failed: %s", exc)
            await wizard_service.clear(db, user.id)
            await send_message(chat_id=chat_id, text=f"Không thể đánh dấu: {exc}")
            return
    else:
        # FLOW_REAL_ESTATE: create asset + mark in same transaction.
        initial = Decimal(str(draft.get("initial_value") or 0))
        current = Decimal(str(draft.get("current_value") or 0))
        if current <= 0:
            await wizard_service.clear(db, user.id)
            await send_message(
                chat_id=chat_id,
                text="Có lỗi với wizard. Thử lại bằng /assets nhé.",
            )
            return
        if initial <= 0:
            initial = current
        extra = dict(draft.get("extra") or {})
        asset = await asset_service.create_asset(
            db,
            user.id,
            asset_type=AssetType.REAL_ESTATE.value,
            subtype=draft.get("subtype"),
            name=draft.get("name") or "Bất động sản",
            initial_value=initial,
            current_value=current,
            extra=extra,
        )
        asset = await rental_service.mark_as_rental(
            db,
            user.id,
            asset.id,
            metadata,
        )

    analytics.track(
        AssetEvent.RENTAL_MARKED,
        user_id=user.id,
        properties={
            "asset_id": str(asset.id),
            "occupancy_status": metadata.occupancy_status,
            "monthly_rent": float(metadata.monthly_rent),
            "mode": mode or "create",
        },
    )

    monthly_rent = Decimal(metadata.monthly_rent)
    monthly_expenses = Decimal(metadata.monthly_expenses)
    yield_pct = metadata.annual_yield_pct(asset.current_value or Decimal(1))
    await send_message(
        chat_id=chat_id,
        text=format_rental_marked(
            asset,
            monthly_rent,
            monthly_expenses,
            yield_pct,
            metadata.occupancy_status,
        ),
        parse_mode="HTML",
    )
    # Diverge here: a freshly-created rental came through the asset
    # wizard so ``_post_save`` (with its add_more_keyboard + undo
    # button) is the right footer. A pre-existing asset getting
    # marked must NOT expose the undo button — its callback
    # (``asset_add:undo:<id>``) hard-deletes the asset, which would
    # silently destroy a user's real-estate row that they only
    # wanted to flag as rental. ``_post_mark_existing`` is the
    # safe completion path.
    if mode == "mark_existing":
        await _post_mark_existing(db, chat_id, user, asset)
    else:
        await _post_save(db, chat_id, user, asset)


# ---------- Mark-existing-as-rental flow (post-creation entry) -------


async def start_mark_rental_wizard(db: AsyncSession, chat_id: int, user: User) -> None:
    """Menu entry: list non-rental real-estate assets, let user pick."""
    candidates = await asset_service.get_user_assets(
        db,
        user.id,
        asset_type=AssetType.REAL_ESTATE.value,
    )
    candidates = [a for a in candidates if not a.is_rental]
    if not candidates:
        await send_message(
            chat_id=chat_id,
            text=(
                "🏠 Bạn chưa có BĐS nào (hoặc đã đánh dấu cho thuê hết rồi).\n\n"
                "Thêm BĐS mới qua /menu → 💎 Tài sản → ➕ Thêm tài sản."
            ),
        )
        return

    items = [(a.id, f"🏠 {a.name}") for a in candidates]
    await send_message(
        chat_id=chat_id,
        text="🏠 <b>Đánh dấu BĐS nào là cho thuê?</b>",
        parse_mode="HTML",
        reply_markup=rental_pick_existing_keyboard(items),
    )


async def _handle_rental_pick(
    db: AsyncSession, chat_id: int, user: User, asset_id_str: str
) -> None:
    """User picked an existing real-estate asset to mark as rental."""
    try:
        asset_id = uuid.UUID(asset_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy BĐS.")
        return

    asset = await asset_service.get_asset_by_id(db, user.id, asset_id)
    if asset is None or asset.asset_type != AssetType.REAL_ESTATE.value:
        await send_message(chat_id=chat_id, text="Không tìm thấy BĐS.")
        return
    if asset.is_rental:
        await send_message(
            chat_id=chat_id,
            text=f"BĐS '{asset.name}' đã được đánh dấu cho thuê rồi.",
        )
        return

    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_MARK_RENTAL,
        step="rental_rent",
        draft={
            "mode": "mark_existing",
            "target_asset_id": str(asset_id),
            "rental": {},
        },
    )
    analytics.track(
        AssetEvent.RENTAL_FLOW_OPENED,
        user_id=user.id,
        properties={"mode": "mark_existing"},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đánh dấu <b>{asset.name}</b> là BĐS cho thuê.\n\n"
            "💰 <b>Tiền thuê hàng tháng?</b>\n"
            "Ví dụ: <code>15tr</code>"
        ),
        parse_mode="HTML",
    )


# ---------- Save / cleanup --------------------------------------------


async def _post_mark_existing(
    db: AsyncSession, chat_id: int, user: User, asset
) -> None:
    """Finalise the FLOW_MARK_RENTAL path.

    Distinct from ``_post_save`` (the create-asset finaliser) to
    avoid two specific footguns:

    1. ``_post_save`` shows ``add_more_keyboard(undo_asset_id=...)``.
       The undo callback hard-deletes the referenced asset. In the
       mark-existing flow that's the user's pre-existing real-estate
       row — tapping undo would silently destroy actual financial
       state, not roll back a mis-entered draft. (Codex P1 flagged
       this on PR #225.)

    2. ``_post_save`` tracks an ``ASSET_ADDED`` analytics event and
       formats the message as "Đã ghi <asset>". Neither is true here:
       the asset already existed, only its rental_metadata changed.

    We still clear wizard state, recompute net worth (rental status
    can affect briefing logic via the income stream), and recompute
    wealth level — those side effects are correct in both flows.
    """
    await wizard_service.clear(db, user.id)

    breakdown = await net_worth_calculator.calculate(db, user.id)
    await update_user_level(db, user.id, breakdown.total)
    # Mark first-asset onboarding step done if this somehow IS their
    # first interaction (rare — would mean they'd added a property
    # without going through onboarding).
    await _mark_onboarding_first_asset_done(db, user)

    await send_message(
        chat_id=chat_id,
        text="✅ Xong! Gõ /menu để xem các tính năng khác.",
    )


async def _post_save(db: AsyncSession, chat_id: int, user: User, asset) -> None:
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
    (FLOW_CRYPTO, "symbol"): _handle_crypto_symbol_input,
    (FLOW_CRYPTO, "quantity"): _handle_crypto_quantity_input,
    (FLOW_CRYPTO, "avg_price"): _handle_crypto_avg_price_input,
    (FLOW_CRYPTO, "current_price_input"): _handle_crypto_current_price_input,
    (FLOW_GOLD, "quantity"): _handle_gold_quantity_input,
    (FLOW_GOLD, "avg_price"): _handle_gold_avg_price_input,
    (FLOW_GOLD, "current_price_input"): _handle_gold_current_price_input,
    (FLOW_REAL_ESTATE, "name"): _handle_re_name_input,
    (FLOW_REAL_ESTATE, "initial_value"): _handle_re_initial_value_input,
    (FLOW_REAL_ESTATE, "current_value"): _handle_re_current_value_input,
    # Phase 3.8 — rental sub-wizard, shared between FLOW_REAL_ESTATE
    # (creation path) and FLOW_MARK_RENTAL (post-creation path).
    (FLOW_REAL_ESTATE, "rental_rent"): _handle_rental_rent_input,
    (FLOW_REAL_ESTATE, "rental_expenses"): _handle_rental_expenses_input,
    (FLOW_REAL_ESTATE, "rental_tenant_input"): _handle_rental_tenant_input,
    (FLOW_REAL_ESTATE, "rental_lease_input"): _handle_rental_lease_input,
    (FLOW_MARK_RENTAL, "rental_rent"): _handle_rental_rent_input,
    (FLOW_MARK_RENTAL, "rental_expenses"): _handle_rental_expenses_input,
    (FLOW_MARK_RENTAL, "rental_tenant_input"): _handle_rental_tenant_input,
    (FLOW_MARK_RENTAL, "rental_lease_input"): _handle_rental_lease_input,
    (FLOW_EDIT_ASSET, "current_value"): _handle_edit_current_value_input,
}


async def handle_asset_text_input(db: AsyncSession, message: dict) -> bool:
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
        logger.exception(
            "asset wizard text handler crashed: flow=%s step=%s", flow, step
        )
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
        await send_message(
            chat_id=chat_id, text="Đã huỷ. Quay lại lúc nào cũng được 👋"
        )
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
            AssetType.CRYPTO.value: _start_crypto_subtype_pick,
            AssetType.GOLD.value: _start_gold_subtype_pick,
            AssetType.REAL_ESTATE.value: _start_real_estate_subtype_pick,
        }
        starter = starters.get(arg)
        if starter is None:
            # Other: not wired yet.
            await send_message(
                chat_id=chat_id,
                text=(
                    "Loại này sẽ có sớm 🙏 Tạm thời bạn dùng 💵 / 📈 / 🏠 / ₿ / 🥇 nhé."
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

    if action == "crypto_subtype" and arg:
        await _handle_crypto_subtype_pick(db, chat_id, user, arg)
        return

    if action == "re_subtype" and arg:
        await _handle_re_subtype_pick(db, chat_id, user, arg)
        return

    if action == "gold_subtype" and arg:
        await _handle_gold_subtype_pick(db, chat_id, user, arg)
        return

    if action == "stock_price" and arg in ("same", "new"):
        draft = wizard_service.get_draft(user.wizard_state)
        await _handle_stock_current_price_choice(db, chat_id, user, arg, draft)
        return

    if action == "crypto_price" and arg in ("same", "new"):
        draft = wizard_service.get_draft(user.wizard_state)
        await _handle_crypto_current_price_choice(db, chat_id, user, arg, draft)
        return

    if action == "gold_price" and arg in ("same", "new"):
        draft = wizard_service.get_draft(user.wizard_state)
        await _handle_gold_current_price_choice(db, chat_id, user, arg, draft)
        return

    if action == "rental_ask" and arg in ("yes", "no"):
        draft = wizard_service.get_draft(user.wizard_state)
        await _handle_rental_ask_choice(db, chat_id, user, arg, draft)
        return

    if action == "rental_status" and arg:
        draft = wizard_service.get_draft(user.wizard_state)
        await _handle_rental_status_choice(db, chat_id, user, arg, draft)
        return

    if action == "rental_extra" and arg:
        draft = wizard_service.get_draft(user.wizard_state)
        await _handle_rental_extra_choice(db, chat_id, user, arg, draft)
        return


async def handle_asset_rental_callback(db: AsyncSession, callback_query: dict) -> bool:
    """Route ``asset_rental:*`` callbacks (mark-existing flow only).

    Distinct from ``asset_add:*`` because the entry point doesn't go
    through the type picker — the user picked an existing real-estate
    row from the menu and we land directly in the rental sub-wizard.
    Returns True iff the callback was consumed.
    """
    data: str = callback_query.get("data") or ""
    if not data.startswith("asset_rental"):
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
    action = parts[0] if parts else ""
    arg = parts[1] if len(parts) > 1 else None

    async def _act() -> None:
        if action == "cancel":
            await wizard_service.clear(db, user.id)
            analytics.track(AssetEvent.WIZARD_CANCELED, user_id=user.id)
            await send_message(chat_id=chat_id, text="Đã huỷ. 👋")
            return
        if action == "pick" and arg:
            await _handle_rental_pick(db, chat_id, user, arg)
            return

    await asyncio.gather(answer_callback(callback_id), _act())
    return True


async def handle_dashboard_callback(db: AsyncSession, callback_query: dict) -> bool:
    """Route dashboard row actions.

    New callbacks use ``asset:*`` per Issue #412. The legacy
    ``dashboard:edit:*`` shape remains accepted so old inline keyboards do
    not break for users with a stale Telegram message.
    """
    data: str = callback_query.get("data") or ""
    if not (data.startswith("asset:") or data.startswith("dashboard:")):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    telegram_id = (callback_query.get("from") or {}).get("id")
    if chat_id is None or telegram_id is None:
        await answer_callback(callback_id)
        return True

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(callback_id, text="Bạn cần /start trước nhé.")
        return True

    prefix, parts = parse_callback(data)
    action = parts[0] if parts else ""
    arg = parts[1] if len(parts) > 1 else None

    async def _act() -> None:
        if action == "sort" and arg:
            sort_key = normalize_sort(arg)
            _DASHBOARD_SORT_BY_USER[user.id] = sort_key
            await show_asset_dashboard_report(
                db, chat_id, user, sort=sort_key, message_id=message_id
            )
            return
        if action == "edit" and arg:
            await start_asset_edit_wizard(
                db, chat_id, user, arg, dashboard_message_id=message_id
            )
            return
        if prefix == "asset" and action == "delete" and arg:
            await _confirm_dashboard_asset_delete(db, chat_id, message_id, user, arg)
            return
        if prefix == "asset" and action == "delete_yes" and arg:
            await _soft_delete_dashboard_asset(db, chat_id, message_id, user, arg)
            return
        if prefix == "asset" and action == "delete_no":
            await show_asset_dashboard_report(
                db, chat_id, user, sort=arg, message_id=message_id
            )
            return
        await send_message(chat_id=chat_id, text="Mình chưa hỗ trợ thao tác này.")

    await asyncio.gather(answer_callback(callback_id), _act())
    return True


async def handle_asset_manage_callback(db: AsyncSession, callback_query: dict) -> bool:
    """Route ``asset_manage:*`` callbacks for edit/delete flows."""
    data: str = callback_query.get("data") or ""
    if not data.startswith("asset_manage"):
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
    action = parts[0] if parts else "menu"
    arg = parts[1] if len(parts) > 1 else None

    async def _act() -> None:
        if action == "menu":
            await show_asset_manage_menu(db, chat_id, user)
            return
        if action == "edit_type" and arg:
            await show_asset_edit_list(db, chat_id, user, arg)
            return
        if action == "edit" and arg:
            return_asset_type = parts[2] if len(parts) > 2 else None
            await start_asset_edit_wizard(
                db,
                chat_id,
                user,
                arg,
                return_to_dashboard=False,
                return_to_portfolio=return_asset_type,
            )
            return
        if action == "delete_type" and arg:
            await show_asset_delete_list(db, chat_id, user, arg)
            return
        if action == "delete_type":
            await show_asset_delete_type_picker(db, chat_id, user)
            return
        if action == "delete_confirm" and arg:
            await _confirm_asset_delete(db, chat_id, user, arg)
            return
        if action == "delete" and arg:
            await _soft_delete_asset(db, chat_id, user, arg)
            return
        if action == "cancel":
            await send_message(
                chat_id=chat_id, text="Đã huỷ. Quay lại lúc nào cũng được 👋"
            )
            return

    await asyncio.gather(answer_callback(callback_id), _act())
    return True


async def handle_asset_callback(db: AsyncSession, callback_query: dict) -> bool:
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


async def _mark_onboarding_first_asset_done(db: AsyncSession, user: User) -> None:
    """Bridge for P3A-9 — see ``backend.bot.handlers.onboarding`` for usage.

    Imported lazily to avoid a circular import at module load.
    """
    from backend.bot.handlers import onboarding as onboarding_handlers

    await onboarding_handlers.note_first_asset_added_if_needed(db, user)
