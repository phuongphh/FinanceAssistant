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

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.menu_formatter import (
    back_to_main_keyboard,
    format_main_menu,
    format_submenu,
    get_action_copy,
    get_submenu_hint,
    known_categories,
)
from backend.bot.formatters.money import format_money_full
from backend.bot.handlers.free_form_text import _send_outcome
from backend.bot.utils.emoji_animation import message_kwargs_for_animation
from backend.intent.dispatcher import IntentDispatcher
from backend.intent.intents import (
    CLASSIFIER_RULE,
    IntentResult,
    IntentType,
)
from backend.miniapp.urls import expense_dashboard_url, wealth_dashboard_url
from backend.models.user import User
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    answer_callback,
    edit_message_text,
    send_chat_action,
    send_message,
)

if TYPE_CHECKING:
    from backend.wealth.services.net_worth_calculator import NetWorthBreakdown

logger = logging.getLogger(__name__)

_dispatcher = IntentDispatcher()


# -----------------------------------------------------------------
# /menu and /dashboard commands — top-level entry points
# -----------------------------------------------------------------


DASHBOARD_NOT_CONFIGURED_TEXT = (
    "📊 Dashboard chưa sẵn sàng — admin cần cấu hình `MINIAPP_BASE_URL` trước nhé."
)

NET_WORTH_WAIT_DELAY_SECONDS = 0.7


async def cmd_dashboard(db: AsyncSession, chat_id: int, user: User | None) -> None:
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
            "inline_keyboard": [
                [
                    {"text": "Mở Dashboard", "web_app": {"url": url}},
                ]
            ],
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
        chat_id=chat_id,
        text=text,
        parse_mode=None,
        reply_markup=keyboard,
        **message_kwargs_for_animation(text, "submenu"),
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


LEGACY_REDIRECT_TEXT = (
    "✨ Menu đã được nâng cấp với 5 mảng rõ ràng hơn:\n"
    "💎 Tài sản • 💸 Chi tiêu • 💰 Dòng tiền • 🎯 Mục tiêu • 📊 Thị trường\n\n"
    "Gõ /menu để xem giao diện mới nhé!"
)


async def handle_menu_callback(
    db: AsyncSession, callback_query: dict[str, Any]
) -> bool:
    """Route every ``menu:*`` callback. Returns ``True`` once handled.

    Phase 3.6 Epic 3 migration: this handler now owns the entire
    ``menu:*`` namespace. Three buckets:

      * ``menu:main`` / ``menu:<v2_category>`` / ``menu:<cat>:<action>``
        — the new 5-category UX from Epic 1/2.
      * ``menu:<anything_else>`` — V1 flat-menu callbacks fired from
        chat history bubbles deployed before the cutover (e.g.
        ``menu:gmail_scan``, ``menu:ocr``, ``menu:report``). They get
        a friendly redirect to ``/menu`` so the user understands the
        UI moved without thinking the bot is broken.
      * Anything not starting with ``menu:`` — return False so the
        worker keeps dispatching its own prefixes (intent_, asset_,
        briefing:, etc.).

    The redirect path stays for ~1 month post-deploy to cover stale
    chat-history bubbles, then becomes dead code — see the follow-up
    issue noted in ``phase-3.6-retrospective.md``.
    """
    data: str = callback_query.get("data") or ""
    if not data.startswith("menu:"):
        return False

    parts = data.split(":")
    if len(parts) < 2:
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")

    # Resolve the user once up front. The legacy-redirect branch needs
    # ``user_id`` for analytics (so we can group stale-bubble taps by
    # wealth tier) and the V2 branch needs the User row for adaptive
    # rendering. One lookup serves both.
    user = await get_user_by_telegram_id(db, telegram_id) if telegram_id else None

    target = parts[1]
    is_v2 = target == "main" or target == "profile" or target in known_categories()

    if not is_v2:
        # Legacy V1 callback. Acknowledge + send redirect; do NOT
        # surface as an error (users tapped a real button that worked
        # last week — that experience shouldn't change suddenly).
        await answer_callback(callback_id)
        if chat_id is not None:
            await send_message(
                chat_id=chat_id,
                text=LEGACY_REDIRECT_TEXT,
                parse_mode="Markdown",
            )
        analytics.track(
            "menu_legacy_redirect",
            user_id=user.id if user else None,
            properties={"callback": data},
        )
        return True

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
    user_id = user.id
    if target == "main":
        text, keyboard = format_main_menu(user, level=level)
    elif target == "profile":
        from backend.profile.handlers.profile_menu import handle_profile_view

        await handle_profile_view(db, chat_id, user, message_id=message_id)
        analytics.track(
            "profile_viewed",
            user_id=user_id,
            properties={"source": "menu"},
        )
        return
    elif target == "cashflow":
        # Issue #445: show live cashflow overview inline so the user sees
        # meaningful data immediately without a redundant "Tổng quan" tap.
        await _navigate_cashflow(
            db=db, user=user, chat_id=chat_id, message_id=message_id, level=level
        )
        analytics.track("menu_navigated", user_id=user_id, properties={"to": target})
        return
    elif target == "assets":
        # Issue #457: show net_worth inline so the user sees total immediately
        # without an extra "Tổng tài sản" tap — same pattern as cashflow.
        await _navigate_assets(
            db=db, user=user, chat_id=chat_id, message_id=message_id, level=level
        )
        analytics.track("menu_navigated", user_id=user_id, properties={"to": target})
        return
    else:
        text, keyboard = format_submenu(user, target, level=level)

    if message_id is None:
        # Defensive: callbacks should always carry message_id. Fall back
        # to a fresh bubble so the user isn't stuck.
        await send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=None,
            reply_markup=keyboard,
            **message_kwargs_for_animation(text, "submenu"),
        )
        return

    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode=None,
        reply_markup=keyboard,
        **message_kwargs_for_animation(text, "submenu"),
    )
    analytics.track(
        "menu_navigated",
        user_id=user.id,
        properties={"to": target},
    )


async def _navigate_cashflow(
    *,
    db: AsyncSession,
    user: User,
    chat_id: int,
    message_id: int | None,
    level: str | None,
) -> None:
    """Issue #445: render cashflow overview inline when entering the submenu.

    Dispatches QUERY_CASHFLOW and overlays the submenu keyboard so the user
    sees live data + action buttons in one message, removing the old
    redundant "Tổng quan" tap.
    """
    result = IntentResult(
        intent=IntentType.QUERY_CASHFLOW,
        confidence=1.0,
        parameters={},
        raw_text="[menu:cashflow]",
        classifier_used=CLASSIFIER_RULE,
    )
    outcome = await _dispatcher.dispatch(result, user, db)
    _, keyboard = format_submenu(user, "cashflow", level=level)
    hint = get_submenu_hint("cashflow")
    text = (outcome.text or "") + (f"\n\n{hint}" if hint else "")
    anim_kwargs = message_kwargs_for_animation(text, "submenu")
    if message_id is None:
        await send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            **anim_kwargs,
        )
        return
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=keyboard,
        **anim_kwargs,
    )


async def _navigate_assets(
    *,
    db: AsyncSession,
    user: User,
    chat_id: int,
    message_id: int | None,
    level: str | None,
) -> None:
    """Issue #457: render net_worth inline when entering the Tài sản submenu.

    Shows the stored net-worth total immediately alongside the submenu
    keyboard so the user sees meaningful data without an extra tap —
    same pattern as _navigate_cashflow (issue #445).
    """
    from backend.intent.wealth_adapt import decorate, style_for_level
    from backend.wealth.ladder import detect_level
    from backend.wealth.services import net_worth_calculator

    breakdown = await net_worth_calculator.calculate_stored_current(db, user.id)
    _, keyboard = format_submenu(user, "assets", level=level)
    hint = get_submenu_hint("assets")
    name = user.display_name or "bạn"

    if breakdown.total <= 0:
        text = (
            f"💎 {name} chưa có tài sản nào trong hệ thống.\n\n"
            "Tap /themtaisan để mình tính tổng tài sản giúp nhé 🚀"
        )
    else:
        asset_level = detect_level(breakdown.total)
        style = style_for_level(asset_level, breakdown.total)
        lines = [
            f"💰 Tổng tài sản của {name}:",
            f"*{format_money_full(breakdown.total)}*",
            "",
            get_action_copy("action_assets_net_worth", "market_value_note"),
        ]
        if breakdown.asset_count and not style.is_starter:
            lines.append("")
            lines.append(f"_Theo dõi qua {breakdown.asset_count} tài sản_")
        text = decorate("\n".join(lines), style)

    if hint:
        text = text + f"\n\n{hint}"

    anim_kwargs = message_kwargs_for_animation(text, "submenu")
    if message_id is None:
        await send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
            **anim_kwargs,
        )
        return
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
        **anim_kwargs,
    )


# -----------------------------------------------------------------
# Action router — Level 3 leaves
# -----------------------------------------------------------------


# Mapping of (category, action) → which Phase 3.5 intent to synthesise.
# When an action just runs an existing read intent, this table is the
# single source of truth — the dispatcher does the rest (handler call,
# personality wrap, follow-up keyboard).
_INTENT_MAP: dict[tuple[str, str], tuple[IntentType, dict]] = {
    # Tài sản — "Tổng tài sản" uses a direct fast handler because the
    # callback is deterministic and should answer from the already-current
    # asset values without waiting for historical snapshot comparisons.
    # "Báo cáo" is a direct handler now so rows can carry edit callbacks.
    # Chi tiêu — ``report`` and ``by_category`` are now direct handlers
    # (Mini App Dashboard). The intent map only kept them as a fallback
    # before the dashboard shipped; the direct map now wins regardless.
    # Dòng tiền — Phase 3.8 Epic 2 promoted ``income`` to a direct
    # handler (CRUD list view); the rest still synthesise an intent
    # so personality wrap + follow-up keyboards stay consistent.
    # Issue #445: overview is now shown inline on submenu entry (see _navigate);
    # route kept for backward-compat with old chat-history bubbles.
    ("cashflow", "overview"): (IntentType.QUERY_CASHFLOW, {}),
    ("cashflow", "monthly_report"): (
        IntentType.QUERY_CASHFLOW,
        {"focus": "current_month_detail", "time_range": "this_month"},
    ),
    # Issue #445: "Chi tiêu" button replaces "Thu vs Chi"; routes to expense report.
    # ``compare`` kept for backward-compat with old chat-history bubbles.
    ("cashflow", "expenses"): (IntentType.QUERY_EXPENSES, {}),
    ("cashflow", "compare"): (IntentType.QUERY_CASHFLOW, {"compare_months": 6}),
    # ``saving_rate`` button removed (issue #445); kept for old chat-history bubbles.
    ("cashflow", "saving_rate"): (IntentType.QUERY_CASHFLOW, {"focus": "saving_rate"}),
    # Mục tiêu
    # Phase 3.8 Epic 5 — ``goals:list`` is a direct handler (see
    # _DIRECT_HANDLERS). Removed from the intent map so the dispatch
    # order matches: direct handler first, intent map second, advisory
    # third, coming-soon last.
    # Thị trường
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
    # Track after the selected action has rendered. ``analytics.track`` is
    # fire-and-forget, but it still opens a background DB session; doing it
    # before fast read paths can contend for the same connection pool and
    # add visible latency before the user sees a reply.
    track_properties = {"category": category, "action": action}

    # 1. Direct-handler actions.
    direct = _DIRECT_HANDLERS.get((category, action))
    if direct is not None:
        await direct(db=db, user=user, chat_id=chat_id, message_id=message_id)
        analytics.track(
            "menu_action_tapped", user_id=user.id, properties=track_properties
        )
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
        analytics.track(
            "menu_action_tapped", user_id=user.id, properties=track_properties
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
        analytics.track(
            "menu_action_tapped", user_id=user.id, properties=track_properties
        )
        return

    # 4. Genuinely unwired — friendly stub with escape route.
    await _send_coming_soon(chat_id, category, action)
    analytics.track("menu_action_tapped", user_id=user.id, properties=track_properties)


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
            'ví dụ "chi tiêu tháng này" hoặc "tài sản của tôi" — '
            "mình hiểu mà 🌱"
        ),
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard(),
    )
    logger.info("menu coming-soon hit: category=%s action=%s", category, action)


# -----------------------------------------------------------------
# Direct-handler implementations (wizards, prompt-and-wait)
# -----------------------------------------------------------------


async def _send_net_worth_wait(chat_id: int) -> None:
    """Send the net-worth waiting sentence."""
    await send_message(
        chat_id=chat_id,
        text=get_action_copy("action_assets_net_worth", "recalculating_wait"),
        parse_mode="Markdown",
    )


async def _calculate_stored_current_with_wait(
    *, db: AsyncSession, user_id: Any, chat_id: int
) -> "NetWorthBreakdown":
    """Calculate stored net worth and show wait copy after 700ms.

    ``wait_for`` keeps the fast path clean: no background sleep task is
    created unless the calculation actually crosses the threshold.
    ``shield`` prevents the timeout from cancelling the in-flight DB work.
    """
    from backend.wealth.services import net_worth_calculator

    calculation = asyncio.create_task(
        net_worth_calculator.calculate_stored_current(db, user_id)
    )
    try:
        return await asyncio.wait_for(
            asyncio.shield(calculation), timeout=NET_WORTH_WAIT_DELAY_SECONDS
        )
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            await _send_net_worth_wait(chat_id)
        return await calculation


async def _action_assets_net_worth(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Fast menu response for ``Tài sản → Tổng tài sản``.

    A menu callback has an exact intent, so this path intentionally skips
    the generic intent dispatcher, historical snapshot comparisons, and live
    market quote refreshes. The slower free-form ``query_net_worth`` handler
    still provides monthly/YTD change context when the user asks in natural
    language. If the stored-current calculation takes at least 700ms, the
    user gets an explicit waiting sentence before the final total.
    """
    from backend.bot.formatters.money import format_money_short
    from backend.bot.formatters.movers import format_movers_block
    from backend.intent.wealth_adapt import decorate, style_for_level
    from backend.wealth.ladder import detect_level
    from backend.wealth.services import net_worth_calculator

    breakdown = await _calculate_stored_current_with_wait(
        db=db, user_id=user.id, chat_id=chat_id
    )
    name = user.display_name or "bạn"
    if breakdown.total <= 0:
        await send_message(
            chat_id=chat_id,
            text=(
                f"💎 {name} chưa có tài sản nào trong hệ thống.\n\n"
                "Tap /themtaisan để mình tính tổng tài sản giúp nhé 🚀"
            ),
            reply_markup=back_to_main_keyboard(),
        )
        return

    level = detect_level(breakdown.total)
    style = style_for_level(level, breakdown.total)

    # Day-over-day total + per-asset movers — reuses asset_snapshots
    # written by the 02:00 EOD revaluation job. ``calculate_change_from_current``
    # is cheap (one indexed query) and ``get_daily_movers`` is one more.
    change_day = await net_worth_calculator.calculate_change_from_current(
        db, user.id, breakdown.total, period=net_worth_calculator.PERIOD_DAY
    )
    movers = await net_worth_calculator.get_daily_movers(db, user.id)

    lines = [
        f"💰 Tổng tài sản của {name}:",
        f"*{format_money_full(breakdown.total)}*",
    ]
    movers_block = format_movers_block(
        total_pct=change_day.change_percentage if change_day.previous > 0 else None,
        movers=movers,
        total_amount=change_day.change_absolute if change_day.previous > 0 else None,
        amount_formatter=format_money_short,
    )
    if movers_block:
        lines.extend(["", movers_block])
    lines.extend(["", get_action_copy("action_assets_net_worth", "market_value_note")])
    if breakdown.asset_count and not style.is_starter:
        lines.append("")
        lines.append(f"_Theo dõi qua {breakdown.asset_count} tài sản_")

    await send_message(
        chat_id=chat_id,
        text=decorate("\n".join(lines), style),
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard(),
    )


async def _action_assets_report(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Open the wealth Mini App Dashboard — Telegram WebApp button.

    Replaces the legacy inline paginated report. The Mini App is the
    primary CRUD surface for assets (full forms, charts, validation),
    so a single tap straight into the WebView is the lowest-friction
    path. Callback queries can't launch a WebApp directly — we must
    reply with an inline ``web_app`` button (Telegram API constraint).
    """
    url = wealth_dashboard_url(source="menu_assets_report")
    if url is None:
        await send_message(
            chat_id=chat_id,
            text=get_action_copy("action_assets_report", "not_configured"),
            parse_mode="Markdown",
            reply_markup=back_to_main_keyboard(),
        )
        return

    await send_message(
        chat_id=chat_id,
        text=get_action_copy("action_assets_report", "open_dashboard"),
        reply_markup={
            "inline_keyboard": [
                [{"text": get_action_copy("action_assets_report", "miniapp_button"),
                  "web_app": {"url": url}}],
                [{"text": "◀️ Quay về menu", "callback_data": "menu:main"}],
            ],
        },
    )
    analytics.track(
        "menu_action",
        user_id=user.id,
        properties={"category": "assets", "action": "report"},
    )


async def _action_assets_manage(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Combined Add/Edit/Delete asset entry — educates 3 alternative paths.

    Replaces the old separate ``add`` and ``edit`` buttons. The Mini App
    already covers full CRUD, so this surface teaches the three entry
    points (Mini App, natural language, net-worth shortcut) rather than
    spawning another wizard tree.
    """
    name = user.display_name or "bạn"
    title = get_action_copy("action_assets_manage", "title")
    body = get_action_copy("action_assets_manage", "body").format(name=name)
    text = f"{title}\n\n{body}"

    keyboard_rows: list[list[dict[str, Any]]] = []
    url = wealth_dashboard_url(source="menu_assets_manage")
    if url is not None:
        keyboard_rows.append([
            {"text": get_action_copy("action_assets_manage", "open_miniapp_button"),
             "web_app": {"url": url}},
        ])
    keyboard_rows.append([
        {"text": get_action_copy("action_assets_manage", "back_button"),
         "callback_data": "menu:main"},
    ])

    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup={"inline_keyboard": keyboard_rows},
    )
    analytics.track(
        "menu_action",
        user_id=user.id,
        properties={"category": "assets", "action": "manage"},
    )


async def _action_expenses_report(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Open the Expense Dashboard Mini App — mirrors ``_action_assets_report``.

    The dashboard is the primary CRUD surface for expenses (full forms,
    pie chart, inline edit/delete), so a single tap straight into the
    WebView is the lowest-friction path. Callback queries can't launch
    a WebApp directly — we reply with an inline ``web_app`` button.
    """
    url = expense_dashboard_url(source="menu_expenses_report")
    if url is None:
        await send_message(
            chat_id=chat_id,
            text=get_action_copy("action_expenses_report", "not_configured"),
            parse_mode="Markdown",
            reply_markup=back_to_main_keyboard(),
        )
        return

    await send_message(
        chat_id=chat_id,
        text=get_action_copy("action_expenses_report", "open_dashboard"),
        reply_markup={
            "inline_keyboard": [
                [{"text": get_action_copy("action_expenses_report", "miniapp_button"),
                  "web_app": {"url": url}}],
                [{"text": "◀️ Quay về menu", "callback_data": "menu:main"}],
            ],
        },
    )
    analytics.track(
        "menu_action",
        user_id=user.id,
        properties={"category": "expenses", "action": "report"},
    )


async def _action_expenses_manage(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Educate the user on the 3 ways to manage expenses.

    Mirrors :func:`_action_assets_manage` so the visual + UX pattern is
    identical across menus: Mini App link + natural-language tips +
    receipt-photo path.
    """
    name = user.display_name or "bạn"
    title = get_action_copy("action_expenses_manage", "title")
    body = get_action_copy("action_expenses_manage", "body").format(name=name)
    text = f"{title}\n\n{body}"

    keyboard_rows: list[list[dict[str, Any]]] = []
    url = expense_dashboard_url(source="menu_expenses_manage")
    if url is not None:
        keyboard_rows.append([
            {"text": get_action_copy("action_expenses_manage", "open_miniapp_button"),
             "web_app": {"url": url}},
        ])
    keyboard_rows.append([
        {"text": get_action_copy("action_expenses_manage", "ocr_button"),
         "callback_data": "menu:expenses:ocr_prompt"},
    ])
    keyboard_rows.append([
        {"text": get_action_copy("action_expenses_manage", "back_button"),
         "callback_data": "menu:main"},
    ])

    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup={"inline_keyboard": keyboard_rows},
    )
    analytics.track(
        "menu_action",
        user_id=user.id,
        properties={"category": "expenses", "action": "manage"},
    )


async def _action_expenses_ocr_prompt(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Prompt the user to send a receipt photo from the manage guide shortcut.

    The worker's existing photo handler takes over once the user uploads
    an image (Phase 3A OCR flow). Kept tiny because the shortcut just
    nudges into the existing entry point.
    """
    await send_message(
        chat_id=chat_id,
        text=(
            "📷 *Đọc hoá đơn*\n\n"
            "Gửi cho mình ảnh hoá đơn — mình sẽ tự đọc số tiền,"
            " merchant và phân loại giúp bạn."
        ),
        parse_mode="Markdown",
        reply_markup=back_to_main_keyboard(),
    )
    analytics.track(
        "menu_action",
        user_id=user.id,
        properties={"category": "expenses", "action": "ocr_prompt"},
    )


async def _action_expenses_recurring(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Phase 3.8 Epic 3 — render the recurring-patterns list view.

    Replaces the default "coming soon" stub for ``menu:expenses:
    recurring``. Shows existing patterns (with edit/disable/reminder
    toggle) + an "Add new" entry into the wizard.
    """
    from backend.bot.handlers.recurring_entry import show_recurring_list

    await show_recurring_list(db, chat_id, user)


async def _action_cashflow_income(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Phase 3.8 Epic 2 — render the income-streams list view with
    edit/pause/delete buttons + "Add new" entry. Replaces the old
    ``QUERY_INCOME`` intent dispatch (which returned a read-only
    formatted summary) so the menu now supports the full CRUD loop
    without needing a free-form follow-up."""
    from backend.bot.handlers.income_entry import show_income_list

    await show_income_list(db, chat_id, user)


async def _action_cashflow_goals(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Open the existing Goals list from the Cashflow context."""
    from backend.bot.handlers.goal_entry import show_goals_list

    await show_goals_list(
        db,
        chat_id,
        user,
        back_callback="menu:cashflow",
        back_label="◀️ Quay về Dòng tiền",
    )


async def _action_assets_mark_rental(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Phase 3.8 Epic 1 — start the "mark existing real-estate as
    rental" flow. The wizard lists every non-rental real-estate asset
    and lets the user pick one, then collects rent + expenses + status.
    """
    from backend.bot.handlers.asset_entry import start_mark_rental_wizard

    await start_mark_rental_wizard(db, chat_id, user)


async def _action_goals_add(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Phase 3.8 Epic 5 — start the template-driven goal wizard."""
    from backend.bot.handlers.goal_entry import start_goals_wizard

    await start_goals_wizard(db, chat_id, user)


async def _action_goals_list(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Phase 3.8 Epic 5 — list active goals with progress + per-row
    action keyboards. Replaces the previous QUERY_GOALS intent
    dispatch which produced a read-only summary."""
    from backend.bot.handlers.goal_entry import show_goals_list

    await show_goals_list(db, chat_id, user)


# Issue #450 §3 — loading indicator copy. ``PLACEHOLDER`` is what the
# user sees within ~1s of tapping the button; ``TIMEOUT_FALLBACK`` is
# what we substitute in when the LLM doesn't return in time. Both
# stay personality-consistent so the wait doesn't break the Bé Tiền
# tone-of-voice.
_GOALS_ADVISOR_PLACEHOLDER = "⏳ Bé Tiền đang phân tích mục tiêu của bạn..."
_GOALS_ADVISOR_TIMEOUT_FALLBACK = (
    "⏳ Bé Tiền cần thêm thời gian — bạn thử lại sau nhé 💚"
)
_GOALS_ADVISOR_TIMEOUT_SECONDS = 15.0


async def _action_goals_advisor(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Issue #450 §3 — "Gợi ý lộ trình" with loading indicator.

    Without a placeholder the user sees an idle chat for 5-10s while
    the LLM thinks (DeepSeek round-trip + advisory context build) and
    assumes the bot is broken. Steps:

      1. Send typing chat-action — Telegram clears it after 5s but
         the placeholder arrives well before then.
      2. Post a placeholder message; capture its message_id.
      3. Dispatch the advisory intent under a hard timeout so a slow
         LLM doesn't pin a callback worker indefinitely.
      4. Edit the placeholder with the actual response (or a friendly
         fallback if we timed out / errored).
    """
    # Step 1 — typing indicator. Failure here is non-fatal; we just
    # skip the visual cue and the placeholder still gives feedback.
    try:
        await send_chat_action(chat_id, "typing")
    except Exception:
        logger.debug("goals advisor: send_chat_action failed", exc_info=True)

    # Step 2 — placeholder. Capture message_id so we can edit in place.
    placeholder_resp = await send_message(
        chat_id=chat_id, text=_GOALS_ADVISOR_PLACEHOLDER
    )
    placeholder_id: int | None = None
    if placeholder_resp and placeholder_resp.get("ok"):
        placeholder_id = (placeholder_resp.get("result") or {}).get("message_id")

    # Step 3 — dispatch advisory with a hard timeout. ADVISORY hits
    # the LLM in the hot path; the surrounding callback flow already
    # has its own try/except (handle_menu_callback) so we keep the
    # local handling tight.
    prompt = _ADVISORY_MAP[("goals", "advisor")]
    result = IntentResult(
        intent=IntentType.ADVISORY,
        confidence=1.0,
        parameters={},
        raw_text=prompt,
        classifier_used=CLASSIFIER_RULE,
    )
    try:
        outcome = await asyncio.wait_for(
            _dispatcher.dispatch(result, user, db),
            timeout=_GOALS_ADVISOR_TIMEOUT_SECONDS,
        )
        body = outcome.text or _GOALS_ADVISOR_TIMEOUT_FALLBACK
    except asyncio.TimeoutError:
        logger.warning("goals advisor LLM timed out after %ss",
                       _GOALS_ADVISOR_TIMEOUT_SECONDS)
        body = _GOALS_ADVISOR_TIMEOUT_FALLBACK
    except Exception:
        logger.exception("goals advisor dispatch crashed")
        body = _GOALS_ADVISOR_TIMEOUT_FALLBACK

    # Step 4 — replace the placeholder with the real body. If the
    # placeholder send failed (no message_id captured), fall back to a
    # fresh send so the user still sees the response.
    if placeholder_id is not None:
        edited = await edit_message_text(
            chat_id=chat_id,
            message_id=placeholder_id,
            text=body,
        )
        if not edited:
            await send_message(chat_id=chat_id, text=body)
    else:
        await send_message(chat_id=chat_id, text=body)


def _market_portfolio_keyboard(asset_type: str, *, include_search: bool = False) -> dict:
    """Action keyboard for Phase 3.9.5 market portfolio surfaces."""
    rows = [
        [
            {
                "text": "💼 Portfolios của tôi",
                "callback_data": f"menu:market:{asset_type}_portfolio",
            }
        ],
        [
            {
                "text": "✏️ Sửa tài sản",
                "callback_data": f"asset_manage:edit_type:{asset_type}",
            }
        ],
    ]
    if include_search:
        rows.insert(1, [{"text": "🔍 Tìm CK theo mã", "callback_data": "menu:market:stock_search"}])
    rows.append([{"text": "◀️ Quay về Thị trường", "callback_data": "menu:market"}])
    return {"inline_keyboard": rows}



VN30_SYMBOLS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "LPB", "MBB", "MSN", "MWG", "PLX", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]


def _market_back_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": "◀️ Quay về", "callback_data": "menu:market"}]]}


VNINDEX_SCREEN_CACHE_KEY = "menu:vnindex:v1"
VNINDEX_SCREEN_CACHE_TTL_MARKET_OPEN = 60  # 1 min during trading hours
VNINDEX_SCREEN_CACHE_TTL_CLOSED = 300  # 5 min outside trading hours


def _is_vn_market_open(now=None) -> bool:
    """Return True during HOSE trading hours (Mon-Fri 09:00-15:00 ICT).

    A coarse window — we use it only to pick a cache TTL, not for order
    routing — so we don't bother with the lunch break (11:30-13:00) or
    ATC nuances. Off-by-15-minutes here just trades cache freshness for
    a slightly stricter ``if`` and is not worth the complexity.
    """
    from datetime import datetime, timezone, timedelta

    if now is None:
        now = datetime.now(timezone(timedelta(hours=7)))
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    return 9 <= now.hour < 15


async def _action_market_vnindex(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """VNIndex market screen with compact VN30 leaders and clean footer.

    Data sources (consulted in parallel, snapshot is the primary):
      1. ``market_snapshots`` table — populated daily by ``market_service``
         using vnstock (VCI source). Same path used by the morning
         briefing and ``get_market_data`` agent tool, so the three
         surfaces always agree.
      2. Live SSI/VNDIRECT dispatcher — only consulted for VN30 symbols
         missing from snapshot (e.g., the cron just rebooted or a new
         listing was added). The dispatcher has its own Redis cache.

    Caching: the fully rendered Markdown payload is cached under
    ``menu:vnindex:v1`` because the data is market-wide (no PII) and a
    burst of users tapping the menu in the same minute should not all
    fan out to Postgres + live providers. TTL is 60s during market
    hours and 300s otherwise — short enough that the freshness label
    ("Cập nhật: HH:MM") never lies by more than the TTL.
    """
    from decimal import Decimal

    from sqlalchemy import desc, select

    from backend.market_data.client import (
        get_redis_client,
        get_stock_quote,
        get_stock_quotes,
    )
    from backend.models.market_snapshot import MarketSnapshot

    redis = get_redis_client()
    try:
        cached = await redis.get(VNINDEX_SCREEN_CACHE_KEY)
    except Exception:
        cached = None
    if cached:
        text = cached.decode("utf-8") if isinstance(cached, (bytes, bytearray)) else cached
        await send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=_market_back_keyboard(),
        )
        return

    def dec(value) -> Decimal:
        try:
            return Decimal(str(value or 0))
        except Exception:
            return Decimal(0)

    def money(value: Decimal) -> str:
        if value >= Decimal("1000000000"):
            return f"{value / Decimal('1000000000'):.1f} tỷ"
        if value >= Decimal("1000000"):
            return f"{value / Decimal('1000000'):.0f} tr"
        return f"{value:,.0f}đ"

    async def latest_vnindex_snapshot() -> MarketSnapshot | None:
        stmt = (
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_code == "VNINDEX")
            .order_by(desc(MarketSnapshot.snapshot_date))
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def latest_vn30_snapshots() -> dict[str, MarketSnapshot]:
        stmt = (
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_code.in_(VN30_SYMBOLS))
            .order_by(MarketSnapshot.asset_code, desc(MarketSnapshot.snapshot_date))
        )
        rows = (await db.execute(stmt)).scalars().all()
        out: dict[str, MarketSnapshot] = {}
        for s in rows:
            out.setdefault(s.asset_code, s)
        return out

    def row_from_quote(q) -> dict:
        pct = dec(q.metadata.get("change_pct"))
        trading_value = dec(q.metadata.get("trading_value"))
        if trading_value <= 0:
            trading_value = q.price * dec(q.metadata.get("volume"))
        return {
            "symbol": q.symbol,
            "price": q.price,
            "change": dec(q.metadata.get("change")),
            "pct": pct,
            "trading_value": trading_value,
            "stale": q.is_stale,
        }

    def row_from_snapshot(s: MarketSnapshot) -> dict:
        extra = s.extra_data or {}
        price = dec(s.price)
        volume = dec(extra.get("volume"))
        trading_value = dec(extra.get("trading_value"))
        if trading_value <= 0:
            trading_value = price * volume
        return {
            "symbol": s.asset_code,
            "price": price,
            "change": dec(extra.get("change")),
            "pct": dec(s.change_1d_pct),
            "trading_value": trading_value,
            "stale": False,
        }

    # Both snapshot reads are independent — fan them out so the DB does
    # the two queries concurrently and the user waits for the slower one
    # only, not their sum.
    snap, snap_by_code = await asyncio.gather(
        latest_vnindex_snapshot(),
        latest_vn30_snapshots(),
    )

    index_data: dict | None = None
    if snap is not None and snap.price:
        index_data = {
            "price": dec(snap.price),
            "change": dec((snap.extra_data or {}).get("change")),
            "pct": dec(snap.change_1d_pct),
            "updated": snap.snapshot_date.strftime("%d/%m"),
            "stale_note": " · dữ liệu cuối phiên",
        }
    if index_data is None:
        try:
            iq = await get_stock_quote("VNINDEX")
            index_data = {
                "price": iq.price,
                "change": dec(iq.metadata.get("change")),
                "pct": dec(iq.metadata.get("change_pct")),
                "updated": iq.fetched_at.astimezone().strftime("%H:%M %d/%m"),
                "stale_note": " · dữ liệu cũ/ngoài giờ" if iq.is_stale else "",
            }
        except Exception:
            logger.warning("Unable to fetch VNINDEX overview", exc_info=True)

    rows: list[dict] = [row_from_snapshot(s) for s in snap_by_code.values() if s.price]
    missing = [sym for sym in VN30_SYMBOLS if sym not in snap_by_code]
    if missing:
        try:
            quote_map = await get_stock_quotes(missing)
            rows.extend(row_from_quote(q) for q in quote_map.values())
        except Exception:
            logger.warning("Unable to fetch VN30 board live", exc_info=True)

    lines = ["📊 *VNIndex*", ""]
    if index_data is None:
        lines.append("Không tải được điểm VNIndex lúc này. Bạn thử lại sau nhé.")
    else:
        pct = index_data["pct"]
        change = index_data["change"]
        sign = "+" if pct >= 0 else ""
        lines.extend([
            f"Điểm: *{index_data['price']:,.2f}*",
            f"Thay đổi: {sign}{change:,.2f} điểm ({sign}{pct:.2f}%){index_data['stale_note']}",
            f"Cập nhật: {index_data['updated']}",
        ])
    lines.append("")
    if not rows:
        lines.append("VN30 chưa có dữ liệu để xếp hạng.")
    else:
        top_value = sorted(rows, key=lambda x: x["trading_value"], reverse=True)[:5]
        gainers = sorted(rows, key=lambda x: x["pct"], reverse=True)[:5]
        losers = sorted(rows, key=lambda x: x["pct"])[:5]
        lines.append("🏦 *Top 5 VN30 theo GTGD*")
        for item in top_value:
            sign = "+" if item["pct"] >= 0 else ""
            lines.append(f"• {item['symbol']}: {item['price']:,.0f}đ · {sign}{item['pct']:.2f}% · GTGD {money(item['trading_value'])}")
        lines.extend(["", "📈 *Tăng mạnh nhất*"])
        for item in gainers:
            sign = "+" if item["pct"] >= 0 else ""
            lines.append(f"• {item['symbol']}: {sign}{item['pct']:.2f}%")
        lines.extend(["", "📉 *Giảm mạnh nhất*"])
        for item in losers:
            sign = "+" if item["pct"] >= 0 else ""
            lines.append(f"• {item['symbol']}: {sign}{item['pct']:.2f}%")

    text = "\n".join(lines)
    ttl = (
        VNINDEX_SCREEN_CACHE_TTL_MARKET_OPEN
        if _is_vn_market_open()
        else VNINDEX_SCREEN_CACHE_TTL_CLOSED
    )
    try:
        await redis.setex(VNINDEX_SCREEN_CACHE_KEY, ttl, text)
    except Exception:
        logger.debug("Skipping VNIndex screen cache write", exc_info=True)

    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=_market_back_keyboard(),
    )

async def _action_market_stock_board(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Show a stock price board filtered to the user's own portfolio."""
    from decimal import Decimal

    from backend.bot.formatters.money import format_money_short
    from backend.market_data.client import get_stock_quotes
    from backend.wealth.services import asset_service

    assets = await asset_service.get_user_assets(db, user.id, asset_type="stock")
    if not assets:
        await send_message(
            chat_id=chat_id,
            text=(
                "📈 *Bảng giá cổ phiếu của bạn*\n\n"
                f"{get_action_copy('action_market_portfolio', 'stock_empty')}"
            ),
            parse_mode="Markdown",
            reply_markup=_market_portfolio_keyboard("stock", include_search=True),
        )
        return

    tickers = []
    for asset in assets:
        ticker = str((asset.extra or {}).get("ticker") or asset.name or "").upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)

    try:
        quotes = await get_stock_quotes(tickers)
    except Exception:
        logger.exception("Unable to fetch portfolio stock quotes")
        quotes = {}

    lines = [
        "📈 *Bảng giá cổ phiếu của bạn*",
        f"_{get_action_copy('action_market_portfolio', 'stock_hint')}_",
        "",
    ]
    for asset in assets:
        ticker = str((asset.extra or {}).get("ticker") or asset.name or "").upper()
        quote = quotes.get(ticker)
        if quote is not None:
            change = quote.metadata.get("change_pct")
            change_text = ""
            if change is not None:
                pct = Decimal(str(change))
                sign = "+" if pct >= 0 else ""
                change_text = f" · {sign}{pct:.2f}%"
            stale = " · dữ liệu cũ" if quote.is_stale else ""
            lines.append(f"• *{ticker}*: {quote.price:,.0f}đ{change_text}{stale}")
        else:
            lines.append(
                f"• *{ticker}*: {format_money_short(asset.current_value)} _(giá trong portfolio)_"
            )

    await send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_market_portfolio_keyboard("stock", include_search=True),
    )


async def _action_market_crypto_prices(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    from backend.intent.handlers.query_market import QueryMarketHandler

    result = IntentResult(
        intent=IntentType.QUERY_MARKET,
        confidence=1.0,
        parameters={"category": "crypto"},
        raw_text="[menu:market:crypto]",
        classifier_used=CLASSIFIER_RULE,
    )
    text = await QueryMarketHandler().handle(result, user, db)
    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=_market_portfolio_keyboard("crypto"),
    )


async def _action_market_gold_prices(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    from backend.intent.handlers.query_market import QueryMarketHandler

    result = IntentResult(
        intent=IntentType.QUERY_MARKET,
        confidence=1.0,
        parameters={"category": "gold"},
        raw_text="[menu:market:gold]",
        classifier_used=CLASSIFIER_RULE,
    )
    text = await QueryMarketHandler().handle(result, user, db)
    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=_market_portfolio_keyboard("gold"),
    )


async def _action_market_portfolio(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None, asset_type: str
) -> None:
    from backend.intent.handlers.query_portfolio import QueryPortfolioHandler

    result = IntentResult(
        intent=IntentType.QUERY_PORTFOLIO,
        confidence=1.0,
        parameters={"asset_type": asset_type},
        raw_text=f"[menu:market:{asset_type}_portfolio]",
        classifier_used=CLASSIFIER_RULE,
    )
    text = await QueryPortfolioHandler().handle(result, user, db)
    hint_key = f"{asset_type}_hint"
    with contextlib.suppress(KeyError):
        text = f"{text}\n\n_{get_action_copy('action_market_portfolio', hint_key)}_"
    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=_market_portfolio_keyboard(asset_type, include_search=asset_type == "stock"),
    )


async def _action_market_stock_portfolio(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    await _action_market_portfolio(
        db=db, user=user, chat_id=chat_id, message_id=message_id, asset_type="stock"
    )


async def _action_market_crypto_portfolio(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    await _action_market_portfolio(
        db=db, user=user, chat_id=chat_id, message_id=message_id, asset_type="crypto"
    )


async def _action_market_gold_portfolio(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    await _action_market_portfolio(
        db=db, user=user, chat_id=chat_id, message_id=message_id, asset_type="gold"
    )


async def _action_market_stock_search(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    await send_message(
        chat_id=chat_id,
        text=(
            "🔍 *Tìm cổ phiếu theo mã*\n\n"
            "Gõ mã bạn muốn xem, ví dụ: `VNM`, `FPT`, `VCB`. "
            "Mình sẽ lấy giá qua provider SSI khi mã được hỗ trợ."
        ),
        parse_mode="Markdown",
        reply_markup=_market_portfolio_keyboard("stock", include_search=False),
    )



async def _action_twin_view_current(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    from backend.bot.handlers.twin_handler import send_twin_current

    await send_twin_current(db, chat_id=chat_id, user=user)


async def _action_twin_compare_optimal(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    from backend.bot.handlers.twin_handler import send_twin_compare_optimal

    await send_twin_compare_optimal(db, chat_id=chat_id, user=user)


async def _action_twin_open_miniapp(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    from backend.bot.handlers.twin_handler import send_twin_miniapp_link

    await send_twin_miniapp_link(chat_id=chat_id)


async def _action_twin_how_it_works(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    from backend.bot.handlers.twin_handler import send_twin_how_it_works

    await send_twin_how_it_works(chat_id=chat_id)


async def _action_twin_share(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Phase 4.1 Story B.1 — render shareable Twin image on demand."""
    from backend.bot.handlers.twin_handler import send_twin_share

    await send_twin_share(db, chat_id=chat_id, user=user)


async def _action_twin_life_events(
    *, db: AsyncSession, user: User, chat_id: int, message_id: int | None
) -> None:
    """Phase 4B Epic 2 — open the Life Event planner from the Twin menu."""
    from backend.bot.handlers.life_event_entry import cmd_life_events

    await cmd_life_events(db, chat_id, user)

_DIRECT_HANDLERS = {
    ("assets", "net_worth"): _action_assets_net_worth,
    ("assets", "report"): _action_assets_report,
    ("assets", "manage"): _action_assets_manage,
    # Legacy callbacks kept so stale chat-history bubbles (before the
    # add/edit → manage merge) don't dead-end. Both route to the new
    # combined "Thêm/Sửa/Xoá" help surface.
    ("assets", "add"): _action_assets_manage,
    ("assets", "edit"): _action_assets_manage,
    ("assets", "mark_rental"): _action_assets_mark_rental,
    ("expenses", "report"): _action_expenses_report,
    ("expenses", "manage"): _action_expenses_manage,
    ("expenses", "ocr_prompt"): _action_expenses_ocr_prompt,
    # Legacy callbacks kept so stale chat-history bubbles (before the
    # 4-button menu restructure) don't dead-end. ``add`` / ``ocr`` /
    # ``by_category`` now all route to the combined manage guide which
    # teaches the natural-language + photo entry points.
    ("expenses", "add"): _action_expenses_manage,
    ("expenses", "ocr"): _action_expenses_manage,
    ("expenses", "by_category"): _action_expenses_manage,
    ("expenses", "recurring"): _action_expenses_recurring,
    ("cashflow", "income"): _action_cashflow_income,
    ("cashflow", "goals"): _action_cashflow_goals,
    # Phase 3.8 Epic 5 — full CRUD via direct handlers (Phase 3A had
    # stub intents). ``advisor`` still routes via the synthesised
    # ADVISORY intent so the LLM gets to use the new ``get_goals``
    # tool + the projection service for free-form follow-ups.
    ("goals", "add"): _action_goals_add,
    ("goals", "list"): _action_goals_list,
    # Issue #450 §3: advisor uses a direct handler so we can show the
    # loading indicator + placeholder while the LLM works.
    ("goals", "advisor"): _action_goals_advisor,
    # Issue #450 §1: the "Cập nhật tiến độ" submenu button was removed
    # because it duplicated the per-row update button in the list. Keep
    # the legacy callback wired to the list view so old chat-history
    # bubbles don't dead-end on the coming-soon stub.
    ("goals", "update"): _action_goals_list,
    ("market", "vnindex"): _action_market_vnindex,
    ("market", "stocks"): _action_market_stock_board,
    ("market", "crypto"): _action_market_crypto_prices,
    ("market", "gold"): _action_market_gold_prices,
    ("market", "stock_portfolio"): _action_market_stock_portfolio,
    ("market", "crypto_portfolio"): _action_market_crypto_portfolio,
    ("market", "gold_portfolio"): _action_market_gold_portfolio,
    ("market", "stock_search"): _action_market_stock_search,
    ("twin", "view_current"): _action_twin_view_current,
    ("twin", "compare_optimal"): _action_twin_compare_optimal,
    ("twin", "open_miniapp"): _action_twin_open_miniapp,
    ("twin", "how_it_works"): _action_twin_how_it_works,
    ("twin", "share"): _action_twin_share,
    ("twin", "life_events"): _action_twin_life_events,
}


__all__ = [
    "cmd_menu",
    "handle_menu_callback",
]
