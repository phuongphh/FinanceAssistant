"""Phase 3.6 menu handler — three-level navigation entry point.

  Level 1: ``/menu`` command → main menu (5 categories)
  Level 2: tap a category    → sub-menu (4-5 actions + back button)
  Level 3: tap an action     → trigger handler / wizard / Phase 3.5 intent

Navigation between Level 1 and Level 2 uses ``editMessageText`` so the
chat doesn't fill up with menu bubbles. Action results (Level 3) post
as a NEW message so the sub-menu stays visible above for further
interaction — tapping multiple actions doesn't require navigating back
each time.

Coexistence with free-form queries (Epic 2 / Story S9):
  * Telegram routes commands and callbacks separately from text — the
    menu and the Phase 3.5 NL pipeline do not collide by design.
  * Open menu + then typing a free-form query → the query is answered
    in a NEW message; the menu bubble stays put. Old messages are
    never auto-deleted.
  * Open menu while a wizard (``users.wizard_state``) is active →
    the menu opens normally. The wizard state lives in the DB and
    survives the menu render; the user can resume by typing the next
    expected wizard input or tapping ``/huy`` to abort. We deliberately
    do NOT prompt "cancel wizard first" because most wizard restarts
    come from the user wanting a different flow anyway, and the extra
    confirm dialog adds friction.

Layer contract (CLAUDE.md § 0.1):
  * Handler receives an open ``AsyncSession`` from the worker.
  * Services flush only; the worker's ``route_update`` commits.
  * No direct LLM calls from this module — Phase 3.5 dispatcher owns
    them, called via ``classify_and_dispatch`` and synthesised intents.

Action wiring philosophy (Epic 1 plumbing rule):
  * Reuse Phase 3.5 intent handlers via the dispatcher whenever the
    action maps cleanly to an existing intent — keeps personality wrap
    and follow-up buttons consistent across menu and free-form paths.
  * Prompt-and-wait actions (OCR, add expense) just send an instruction
    message. The user's next photo/text falls through to the existing
    ingestion / NL parser routes.
  * Wizard actions (add asset) call the wizard's existing entry point
    so wizard_state is set correctly.
  * Genuinely missing capability → friendly "coming soon" with a hint
    about the free-form alternative. Never silent fail.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.menu_formatter import (
    back_to_main_keyboard,
    format_main_menu,
    format_submenu,
    known_categories,
)
from backend.bot.handlers.free_form_text import _send_outcome
from backend.intent.dispatcher import IntentDispatcher
from backend.intent.intents import (
    CLASSIFIER_RULE,
    IntentResult,
    IntentType,
)
from backend.miniapp.urls import wealth_dashboard_url
from backend.models.user import User
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    answer_callback,
    edit_message_text,
    send_message,
)

logger = logging.getLogger(__name__)

_dispatcher = IntentDispatcher()


# -----------------------------------------------------------------
# /menu and /dashboard commands — top-level entry points
# -----------------------------------------------------------------


DASHBOARD_NOT_CONFIGURED_TEXT = (
    "📊 Dashboard chưa sẵn sàng — admin cần cấu hình "
    "`MINIAPP_BASE_URL` trước nhé."
)


async def cmd_dashboard(
    db: AsyncSession, chat_id: int, user: User | None
) -> None:
    """Handle the ``/dashboard`` command — open the wealth Mini App.

    The Mini App opens in-place inside Telegram, so the user never
    leaves the chat. When ``MINIAPP_BASE_URL`` is unset (dev / first
    deploy without a public host) we send a friendly placeholder
    instead of a broken button — same fallback shape as the briefing
    keyboard to keep the user UX consistent.
    """
    url = wealth_dashboard_url(source="dashboard_command")
    if url is None:
        await send_message(
            chat_id=chat_id,
            text=DASHBOARD_NOT_CONFIGURED_TEXT,
            parse_mode="Markdown",
        )
        return

    await send_message(
        chat_id=chat_id,
        text="📊 Mở dashboard tài sản:",
        reply_markup={
            "inline_keyboard": [[
                {"text": "Mở Dashboard", "web_app": {"url": url}},
            ]],
        },
    )
    if user is not None:
        analytics.track(
            "dashboard_command_opened",
            user_id=user.id,
            properties={"source": "command"},
        )


async def cmd_menu(db: AsyncSession, chat_id: int, user: User | None) -> None:
    """Handle the ``/menu`` command.

    Sends a NEW message (not edit) — the user typed a command, so the
    expected output is a fresh bubble. Subsequent navigation taps
    inside that bubble use edit-in-place.

    Wealth-level adaptive intro: read ``user.wealth_level`` (already
    persisted by the asset wizard via ``ladder.update_user_level``).
    No recompute, no in-memory cache — the column is the source of
    truth and changes only on real life events (asset add/edit), not
    on transient market noise. ``None`` falls back to YOUNG_PROFESSIONAL
    via the formatter's default.
    """
    level = user.wealth_level if user else None
    text, keyboard = format_main_menu(user, level=level)
    await send_message(
        chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=keyboard
    )
    user_id = user.id if user else None
    analytics.track(
        "menu_opened",
        user_id=user_id,
        properties={"source": "command", "level": level},
    )


# -----------------------------------------------------------------
# Callback router — the menu:* prefix dispatches here
# -----------------------------------------------------------------


async def handle_menu_callback(
    db: AsyncSession, callback_query: dict[str, Any]
) -> bool:
    """Route a ``menu:*`` callback. Returns ``True`` if handled.

    Returning ``False`` lets the worker fall through to legacy menu
    callbacks (the V1 flat menu) so the cutover is non-destructive —
    Epic 3 archives the legacy paths. Anything matching the new
    schema (``menu:main`` / ``menu:<known_cat>`` / ``menu:<cat>:<act>``)
    is owned by this handler.
    """
    data: str = callback_query.get("data") or ""
    if not data.startswith("menu:"):
        return False

    parts = data.split(":")
    if len(parts) < 2:
        return False

    target = parts[1]
    if target != "main" and target not in known_categories():
        # Legacy flat-menu callback (e.g. ``menu:ocr``, ``menu:report``).
        # Defer to the legacy handler in the worker.
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")

    user = await get_user_by_telegram_id(db, telegram_id) if telegram_id else None
    if user is None:
        # Edge case: Telegram delivered an old menu bubble after the user
        # was removed from the DB. Friendly nudge instead of a silent fail.
        await answer_callback(
            callback_id,
            text="Mình chưa thấy bạn — gõ /start để mình chào nhé 🌱",
            show_alert=True,
        )
        return True

    # Always answer callback first to dismiss the spinner.
    await answer_callback(callback_id)

    try:
        if len(parts) == 2:
            await _navigate(
                db=db,
                user=user,
                chat_id=chat_id,
                message_id=message_id,
                target=target,
            )
            return True

        # Level 3 — action.
        category = target
        action = parts[2]
        await _route_action(
            db=db,
            user=user,
            chat_id=chat_id,
            message_id=message_id,
            category=category,
            action=action,
        )
        return True
    except Exception:
        # Never crash the callback path — log and reassure the user. The
        # worker's outer try/except still rolls back the DB on flush errors.
        logger.exception("menu callback failed: %s", data)
        await send_message(
            chat_id=chat_id,
            text="Có gì đó không ổn 😔 — bạn thử /menu lại giúp mình nhé.",
        )
        return True


# -----------------------------------------------------------------
# Navigation — main ↔ sub-menu via edit-in-place
# -----------------------------------------------------------------


async def _navigate(
    *,
    db: AsyncSession,
    user: User,
    chat_id: int,
    message_id: int | None,
    target: str,
) -> None:
    """Edit the menu message in place to show ``target``.

    ``target == "main"`` → main menu. Anything else is treated as a
    sub-menu category (already validated by caller).
    """
    level = user.wealth_level
    if target == "main":
        text, keyboard = format_main_menu(user, level=level)
    else:
        text, keyboard = format_submenu(user, target, level=level)

    if message_id is None:
        # Defensive: callbacks should always carry message_id. Fall back
        # to a fresh bubble so the user isn't stuck.
        await send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return

    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    analytics.track(
        "menu_navigated",
        user_id=user.id,
        properties={"to": target},
    )


# -----------------------------------------------------------------
# Action router — Level 3 leaves
# -----------------------------------------------------------------


# Mapping of (category, action) → which Phase 3.5 intent to synthesise.
# When an action just runs an existing read intent, this table is the
# single source of truth — the dispatcher does the rest (handler call,
# personality wrap, follow-up keyboard).
_INTENT_MAP: dict[tuple[str, str], tuple[IntentType, dict]] = {
    # Tài sản
    ("assets", "net_worth"): (IntentType.QUERY_ASSETS, {}),
    ("assets", "report"): (IntentType.QUERY_NET_WORTH, {}),
    # Chi tiêu
    ("expenses", "report"): (IntentType.QUERY_EXPENSES, {}),
    ("expenses", "by_category"): (IntentType.QUERY_EXPENSES_BY_CATEGORY, {}),
    # Dòng tiền
    ("cashflow", "overview"): (IntentType.QUERY_CASHFLOW, {}),
    ("cashflow", "income"): (IntentType.QUERY_INCOME, {}),
    ("cashflow", "compare"): (IntentType.QUERY_CASHFLOW, {"compare_months": 6}),
    ("cashflow", "saving_rate"): (IntentType.QUERY_CASHFLOW, {"focus": "saving_rate"}),
    # Mục tiêu
    ("goals", "list"): (IntentType.QUERY_GOALS, {}),
    ("goals", "update"): (IntentType.QUERY_GOAL_PROGRESS, {}),
    # Thị trường
    ("market", "vnindex"): (IntentType.QUERY_MARKET, {"ticker": "VNINDEX"}),
    ("market", "stocks"): (IntentType.QUERY_PORTFOLIO, {"asset_type": "stock"}),
    ("market", "crypto"): (IntentType.QUERY_MARKET, {"category": "crypto"}),
    ("market", "gold"): (IntentType.QUERY_MARKET, {"category": "gold"}),
}


# Prompts the user with a context phrase that is then dispatched as
# ADVISORY (LLM-routed) — keeps the menu's tư-vấn buttons consistent
# with the free-form "tư vấn ..." voice from Phase 3.5.
_ADVISORY_MAP: dict[tuple[str, str], str] = {
    ("assets", "advisor"): "Tư vấn tối ưu portfolio hiện tại của tôi",
    ("goals", "advisor"): "Lộ trình đạt mục tiêu của tôi như thế nào?",
    ("market", "advisor"): "Cơ hội đầu tư mới hiện nay là gì?",
}


async def _route_action(
    *,
    db: AsyncSession,
    user: User,
    chat_id: int,
    message_id: int | None,
    category: str,
    action: str,
) -> None:
    """Dispatch a Level 3 action to its handler.

    Order of resolution:
      1. Direct handler (wizards, prompts) — actions with side effects
         that don't fit the read-intent shape.
      2. Synthesised read intent via ``_INTENT_MAP``.
      3. Synthesised advisory via ``_ADVISORY_MAP``.
      4. Coming-soon fallback (never crash, always escape route).
    """
    analytics.track(
        "menu_action_tapped",
        user_id=user.id,
        properties={"category": category, "action": action},
    )

    # 1. Direct-handler actions.
    direct = _DIRECT_HANDLERS.get((category, action))
    if direct is not None:
        await direct(db=db, user=user, chat_id=chat_id, message_id=message_id)
        return

    # 2. Synthesised read intent.
    if (category, action) in _INTENT_MAP:
        intent_type, params = _INTENT_MAP[(category, action)]
        await _dispatch_synthesised(
            db=db,
            user=user,
            chat_id=chat_id,
            intent_type=intent_type,
            parameters=params,
            origin=f"menu:{category}:{action}",
        )
        return

    # 3. Advisory.
    if (category, action) in _ADVISORY_MAP:
        prompt = _ADVISORY_MAP[(category, action)]
        await _dispatch_synthesised(
            db=db,
            user=user,
            chat_id=chat_id,
            intent_type=IntentType.ADVISORY,
            parameters={},
            origin=f"menu:{category}:{action}",
            raw_text=prompt,
        )
        return

    # 4. Genuinely unwired — friendly stub with escape route.
    await _send_coming_soon(chat_id, category, action)


async def _dispatch_synthesised(
    *,
    db: AsyncSession,
    user: User,
    chat_id: int,
    intent_type: IntentType,
    parameters: dict,
    origin: str,
    raw_text: str = "",
) -> None:
    """Build an IntentResult at full confidence and dispatch it.

    Reuses the Phase 3.5 dispatcher so the user sees the same
    personality wrapper, follow-up buttons, and analytics as if they'd
    typed the equivalent free-form query.
    """
    result = IntentResult(
        intent=intent_type,
        confidence=1.0,
        parameters=dict(parameters),
        raw_text=raw_text or f"[{origin}]",
        classifier_used=CLASSIFIER_RULE,
    )
    outcome = await _dispatcher.dispatch(result, user, db)
    await _send_outcome(chat_id, outcome)


async def _send_coming_soon(chat_id: int, category: str, action: str) -> None:
    """Friendly fallback for actions that don't have a handler yet."""
    await send_message(
        chat_id=chat_id,
        text=(
            "🚧 Tính năng này mình đang phát triển nhé.\n\n"
            "Trong lúc chờ, bạn có thể hỏi mình thẳng — "
            "ví dụ \"chi tiêu tháng này\" hoặc \"tài sản của tôi\" — "
            "mình hiểu mà 🌱"
        ),
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard(),
    )
    logger.info("menu coming-soon hit: category=%s action=%s", category, action)


# -----------------------------------------------------------------
# Direct-handler implementations (wizards, prompt-and-wait)
# -----------------------------------------------------------------


async def _action_assets_add(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Open the Phase 3A asset-entry wizard."""
    from backend.bot.handlers.asset_entry import start_asset_wizard

    await start_asset_wizard(db, chat_id, user)


async def _action_assets_edit(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Show the user's asset list — full inline-edit wizard is a later
    phase. The list gives the names the user needs to update via
    natural language ("update VCB to 100tr").
    """
    from backend.bot.handlers.asset_entry import list_assets

    await list_assets(db, chat_id, user)


async def _action_expenses_add(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Prompt the user to send a free-text or voice transaction.

    The message they send next falls through the worker's normal
    routes — voice → voice_query, text → handle_text_message which
    runs the NL expense parser.
    """
    await send_message(
        chat_id=chat_id,
        text=(
            "✏️ *Thêm chi tiêu nhanh*\n\n"
            "Gõ hoặc nói cho mình biết, ví dụ:\n"
            "• _\"vừa chi 200k cafe\"_\n"
            "• _\"mua xe máy 35tr\"_\n"
            "• _\"trả tiền điện 1.2tr\"_\n\n"
            "Mình sẽ tự ghi lại và phân loại."
        ),
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard(),
    )


async def _action_expenses_ocr(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Prompt the user to send a receipt photo. Existing photo
    handler in the worker takes over from there (Phase 3A OCR flow).
    """
    await send_message(
        chat_id=chat_id,
        text=(
            "📷 *OCR hóa đơn*\n\n"
            "Gửi cho mình ảnh hóa đơn — mình sẽ tự đọc số tiền,"
            " merchant và phân loại giúp bạn."
        ),
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard(),
    )


async def _action_goals_add(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Add-goal wizard isn't built yet (Phase 4 scope) — guide the
    user to the free-form path that already works via Phase 3.5.
    """
    await send_message(
        chat_id=chat_id,
        text=(
            "🎯 *Thêm mục tiêu mới*\n\n"
            "Mô tả mục tiêu cho mình, ví dụ:\n"
            "• _\"muốn tiết kiệm 50tr trong 6 tháng để mua xe\"_\n"
            "• _\"để dành 200tr cho con đi học năm 2028\"_\n\n"
            "Mình hiểu được khá tốt — cứ kể tự nhiên nhé."
        ),
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard(),
    )


_DIRECT_HANDLERS = {
    ("assets", "add"): _action_assets_add,
    ("assets", "edit"): _action_assets_edit,
    ("expenses", "add"): _action_expenses_add,
    ("expenses", "ocr"): _action_expenses_ocr,
    ("goals", "add"): _action_goals_add,
}


__all__ = [
    "cmd_menu",
    "handle_menu_callback",
]
