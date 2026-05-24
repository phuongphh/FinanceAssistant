"""Background worker for Telegram updates.

The webhook route claims an ``update_id`` row and spawns
``process_update_safely`` via ``asyncio.create_task``. This module owns:

- ``route_update`` — dispatch a raw Telegram update dict to the right
  handler (message / callback / onboarding). Opens its own DB session
  because the webhook's session has already been closed by the time the
  background task runs.
- ``process_update_safely`` — never-raise wrapper that marks the
  ``telegram_updates`` row as done/failed.
- ``recover_orphaned_updates`` — scan for rows stuck in ``processing``
  at startup and re-enqueue them.

See docs/archive/scaling-refactor-A.md §A3 + §A1 for context.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session_factory
from backend.models.telegram_update import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    TelegramUpdate,
)

logger = logging.getLogger(__name__)

# How long a row can sit in ``processing`` before we consider it orphaned.
# Long enough that a genuinely slow handler isn't re-run, short enough
# that a crashed worker's work is retried quickly.
ORPHAN_CUTOFF = timedelta(minutes=5)

# Cap orphan pickup per startup to avoid a thundering herd after a long
# outage. Anything over this stays for the next restart or a human to
# inspect.
ORPHAN_BATCH_LIMIT = 100


def _normalize_text_command(text: str) -> str:
    """Return a comparable Telegram command token from message text.

    Telegram can deliver bot-menu commands as ``/about@BotUsername`` in
    group-like contexts, and deep links can arrive as ``/start payload``.
    Routing should match the command name, not the mention suffix or args.
    """
    stripped = text.strip().lower()
    if not stripped.startswith("/"):
        return stripped

    command_token = stripped.split(maxsplit=1)[0]
    command_name, _, _bot_username = command_token.partition("@")
    return command_name


async def route_update(data: dict) -> None:
    """Dispatch one Telegram update to the right handler.

    Opens a fresh ``AsyncSession`` — the webhook's session is long gone
    by the time this runs in a background task. Commits on success,
    rolls back on exception (the caller marks the row status).
    """
    # Imports are local to avoid a module-import cycle with routers/
    # and to keep worker startup cheap (handlers pull in Telegram SDK
    # HTTP clients which open sockets on import).
    from backend.bot.handlers import about_handler as about_handlers
    from backend.bot.handlers import asset_entry as asset_entry_handlers
    from backend.bot.handlers import briefing as briefing_handlers
    from backend.bot.handlers import goal_entry as goal_entry_handlers
    from backend.bot.handlers import income_entry as income_entry_handlers
    from backend.bot.handlers import life_event_entry as life_event_entry_handlers
    from backend.bot.handlers import onboarding as onboarding_handlers
    from backend.bot.handlers import positioning_survey as positioning_survey_handlers
    from backend.bot.handlers import recurring_entry as recurring_entry_handlers
    from backend.bot.handlers import storytelling as storytelling_handlers
    from backend.feedback.handlers import feedback_command as feedback_handlers
    from backend.profile.handlers import profile_menu as profile_handlers
    from backend.bot.handlers.callbacks import handle_transaction_callback
    from backend.bot.handlers.menu_handler import (
        handle_menu_callback as handle_menu_v2_callback,
    )
    from backend.bot.handlers.message import (
        handle_report_command,
        handle_text_message,
    )
    from backend.bot.personality.onboarding_flow import OnboardingStep
    from backend.services import dashboard_service
    from backend.services.telegram_service import answer_callback
    from backend import analytics

    update_id = data.get("update_id")
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            user_id = None
            message = data.get("message")
            if message:
                user_id = await _handle_message(
                    db,
                    message,
                    onboarding_handlers=onboarding_handlers,
                    asset_entry_handlers=asset_entry_handlers,
                    income_entry_handlers=income_entry_handlers,
                    recurring_entry_handlers=recurring_entry_handlers,
                    goal_entry_handlers=goal_entry_handlers,
                    life_event_entry_handlers=life_event_entry_handlers,
                    storytelling_handlers=storytelling_handlers,
                    feedback_handlers=feedback_handlers,
                    profile_handlers=profile_handlers,
                    dashboard_service=dashboard_service,
                    handle_report_command=handle_report_command,
                    handle_text_message=handle_text_message,
                    OnboardingStep=OnboardingStep,
                    analytics=analytics,
                )
            else:
                callback_query = data.get("callback_query")
                if callback_query:
                    user_id = await _handle_callback(
                        db,
                        callback_query,
                        about_handlers=about_handlers,
                        onboarding_handlers=onboarding_handlers,
                        asset_entry_handlers=asset_entry_handlers,
                        income_entry_handlers=income_entry_handlers,
                        recurring_entry_handlers=recurring_entry_handlers,
                        goal_entry_handlers=goal_entry_handlers,
                        life_event_entry_handlers=life_event_entry_handlers,
                        briefing_handlers=briefing_handlers,
                        storytelling_handlers=storytelling_handlers,
                        feedback_handlers=feedback_handlers,
                        profile_handlers=profile_handlers,
                        positioning_survey_handlers=positioning_survey_handlers,
                        dashboard_service=dashboard_service,
                        handle_transaction_callback=handle_transaction_callback,
                        handle_menu_v2_callback=handle_menu_v2_callback,
                        answer_callback=answer_callback,
                    )

            # Stamp the resolved user_id on the queue row so we can
            # replay / audit / delete updates per-user. Best-effort —
            # rows for unknown Telegram IDs stay with user_id NULL.
            if update_id is not None and user_id is not None:
                await db.execute(
                    sa_update(TelegramUpdate)
                    .where(TelegramUpdate.update_id == update_id)
                    .values(user_id=user_id)
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def _reject_if_suspended(
    db: AsyncSession, *, telegram_id: int | None, chat_id: int, dashboard_service
) -> bool:
    if telegram_id is None:
        return False
    user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
    if user is None or getattr(user, "manual_status", None) != "suspended":
        return False
    from backend.services.telegram_service import send_message

    await send_message(
        chat_id,
        "Tài khoản của bạn đang tạm khóa. Vui lòng liên hệ admin@nuitruc.ai để được hỗ trợ.",
        parse_mode=None,
    )
    return True


async def _handle_message(
    db: AsyncSession,
    message: dict,
    *,
    onboarding_handlers,
    asset_entry_handlers,
    income_entry_handlers,
    recurring_entry_handlers,
    goal_entry_handlers,
    life_event_entry_handlers,
    storytelling_handlers,
    feedback_handlers,
    profile_handlers,
    dashboard_service,
    handle_report_command,
    handle_text_message,
    OnboardingStep,
    analytics,
):
    """Dispatch a message update. Returns the resolved internal user_id
    (or None if the sender isn't yet registered) so ``route_update`` can
    stamp it on the telegram_updates row.
    """
    text = message.get("text", "")
    chat_id = message["chat"]["id"]
    command = _normalize_text_command(text)
    from_user = message.get("from") or {}
    telegram_id = from_user.get("id")

    if await _reject_if_suspended(
        db,
        telegram_id=telegram_id,
        chat_id=chat_id,
        dashboard_service=dashboard_service,
    ):
        resolved_user = (
            await dashboard_service.get_user_by_telegram_id(db, telegram_id)
            if telegram_id is not None
            else None
        )
        return resolved_user.id if resolved_user else None

    if command == "/start":
        if telegram_id is None:
            analytics.track(
                analytics.EventType.BOT_STARTED,
                properties={"has_telegram_id": False, "new_user": False},
            )
            return None

        user, created = await dashboard_service.get_or_create_user(
            db,
            telegram_id,
            first_name=from_user.get("first_name"),
            last_name=from_user.get("last_name"),
            username=from_user.get("username"),
        )
        analytics.track(
            analytics.EventType.BOT_STARTED,
            user_id=user.id,
            properties={
                "new_user": created,
                "is_onboarded": user.is_onboarded,
                "has_display_name": bool(user.display_name),
            },
        )

        # Phase 4.1 — V2 goal-based onboarding for new users. Existing
        # users (already past welcome step) stay on the legacy flow so
        # their state isn't reset mid-onboarding.
        from backend.bot.handlers import onboarding_v2

        # Deep-link payload follows "/start " (Telegram convention).
        payload: str | None = None
        if " " in text.strip():
            payload = text.strip().split(maxsplit=1)[1]

        use_v2 = onboarding_v2.is_v2_enabled() and (
            created or user.onboarding_step <= int(OnboardingStep.NOT_STARTED)
        )
        if use_v2:
            await onboarding_v2.handle_start(db, chat_id, user, payload=payload)
        else:
            await onboarding_handlers.resume_or_start(db, chat_id, user)
        return user.id

    if command == "/about":
        # Product metadata is static and does not require a user lookup,
        # keeping the command fast even for first-time users.
        from backend.bot.handlers.about_handler import cmd_about

        await cmd_about(chat_id)
        return None

    if command in ("/menu", "menu", "/dashboard"):
        # Phase 3.6 — both top-level commands resolve the user up front so
        # the menu adapts to ``user.wealth_level`` (Epic 2) and
        # ``/dashboard`` can attribute analytics. ``/menu`` opens the rich
        # 5-category inline menu; ``/dashboard`` opens the wealth Mini App.
        from backend.bot.handlers.menu_handler import cmd_dashboard, cmd_menu

        resolved_user = (
            await dashboard_service.get_user_by_telegram_id(db, telegram_id)
            if telegram_id is not None
            else None
        )
        if command == "/dashboard":
            await cmd_dashboard(db, chat_id, resolved_user)
        else:
            await cmd_menu(db, chat_id, resolved_user)
        return resolved_user.id if resolved_user else None

    if command == "/baocaosang":
        from backend.bot.handlers.morning_briefing_command import (
            send_morning_briefing_now,
        )

        resolved_user = (
            await dashboard_service.get_user_by_telegram_id(db, telegram_id)
            if telegram_id is not None
            else None
        )
        await send_morning_briefing_now(
            db,
            chat_id=chat_id,
            user=resolved_user,
        )
        return resolved_user.id if resolved_user else None

    if command == "/report":
        await handle_report_command(db, message)
        if telegram_id is not None:
            user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
            return user.id if user else None
        return None

    # Resolve the user once up front for the remaining text-message
    # paths — all of them need it (either to detect the onboarding step
    # or to stamp user_id on the queue row).
    resolved_user = None
    if telegram_id is not None:
        resolved_user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)

    # /taisan — list all active assets for the user.
    if command == "/taisan":
        if resolved_user is not None:
            await asset_entry_handlers.list_assets(db, chat_id, resolved_user)
            return resolved_user.id
        return None

    # /assets — open the asset-entry wizard (Phase 3A).
    if command in ("/assets", "/asset", "/themtaisan"):
        if resolved_user is not None:
            await asset_entry_handlers.start_asset_wizard(db, chat_id, resolved_user)
            return resolved_user.id
        return None

    # /life_events — open the life-event planner menu (Phase 4B Epic 2).
    if command in ("/life_events", "/lifeevents", "/kehoach", "/kế_hoạch"):
        await life_event_entry_handlers.cmd_life_events(db, chat_id, resolved_user)
        return resolved_user.id if resolved_user else None

    # Phase 4B Epic 4 — Zalo linking commands. Both are user-scoped so
    # we route them by command name regardless of wizard state.
    if command in ("/link_zalo", "/linkzalo", "/lien_ket_zalo"):
        from backend.bot.handlers.zalo_linking import cmd_link_zalo

        await cmd_link_zalo(db, chat_id, resolved_user)
        return resolved_user.id if resolved_user else None

    if command in ("/unlink_zalo", "/unlinkzalo", "/huy_lien_ket_zalo"):
        from backend.bot.handlers.zalo_linking import cmd_unlink_zalo

        await cmd_unlink_zalo(db, chat_id, resolved_user)
        return resolved_user.id if resolved_user else None

    # /feedback — zero-friction feedback capture (Phase 3.8.5 Epic 1).
    if command == "/feedback":
        if resolved_user is not None:
            await feedback_handlers.start_feedback(db, chat_id, resolved_user)
            return resolved_user.id
        return None

    # Phase 4.1 Story A.7 — operator triage commands. Auth (operator
    # telegram_id check) happens inside the handler so the unauthorized
    # message is rendered consistently.
    if command == "/feedback_inbox":
        from backend.feedback.handlers import triage_command

        await triage_command.cmd_feedback_inbox(db, chat_id, telegram_id)
        return resolved_user.id if resolved_user else None

    if command == "/feedback_reply":
        from backend.feedback.handlers import triage_command

        await triage_command.cmd_feedback_reply(db, chat_id, telegram_id, text)
        return resolved_user.id if resolved_user else None

    # Phase 4.1 Story C.4 — founding-member commands.
    if command == "/whoami":
        from backend.bot.handlers import founding_handler

        await founding_handler.cmd_whoami(db, chat_id, resolved_user)
        return resolved_user.id if resolved_user else None

    if command == "/founding_status":
        from backend.bot.handlers import founding_handler

        await founding_handler.cmd_founding_status(db, chat_id, telegram_id)
        return resolved_user.id if resolved_user else None

    if command == "/cohort_stats":
        from backend.bot.handlers import founding_handler

        await founding_handler.cmd_cohort_stats(db, chat_id, telegram_id)
        return resolved_user.id if resolved_user else None

    # /story or /kechuyen — open storytelling mode (Phase 3A Epic 3).
    if command in ("/story", "/kechuyen", "/kể_chuyện"):
        if resolved_user is not None:
            await storytelling_handlers.handle_storytelling_command(
                db, chat_id, resolved_user
            )
            return resolved_user.id
        return None

    # /huy or /cancel — escape hatch out of any active wizard. Tries the
    # asset wizard first; if that wasn't active, falls back to
    # storytelling. Either flow's text mode otherwise blocks NL parsing,
    # so the user needs a non-button way to bail.
    if command in ("/huy", "/cancel"):
        if resolved_user is not None:
            flow = (resolved_user.wizard_state or {}).get("flow") or ""
            if flow == profile_handlers.FLOW_PROFILE:
                await profile_handlers.handle_profile_text_input(db, message)
            elif flow == feedback_handlers.FLOW_FEEDBACK:
                await feedback_handlers.handle_feedback_text_input(db, message)
            elif flow in life_event_entry_handlers.ALL_FLOWS:
                await life_event_entry_handlers.cancel_wizard(
                    db, chat_id, resolved_user
                )
            elif await goal_entry_handlers.cancel_wizard(db, chat_id, resolved_user):
                pass
            elif not await asset_entry_handlers.cancel_wizard(
                db, chat_id, resolved_user
            ):
                await storytelling_handlers.cancel_storytelling(
                    db, chat_id, resolved_user
                )
            return resolved_user.id
        return None

    # Storytelling voice input — only meaningful while in storytelling
    # mode. Routed BEFORE the asset wizard text dispatch because voice
    # messages have no ``text`` field and would fall through otherwise.
    if (
        message.get("voice")
        and resolved_user is not None
        and (resolved_user.wizard_state or {}).get("flow")
        == storytelling_handlers.FLOW_STORYTELLING
    ):
        consumed = await storytelling_handlers.handle_storytelling_input(db, message)
        if consumed:
            return resolved_user.id

    # Phase 3.5 — voice OUTSIDE storytelling = free-form query. Runs
    # AFTER the storytelling branch so a user mid-story doesn't get
    # their voice misrouted; before the text fallthrough so plain
    # voice messages aren't ignored.
    if message.get("voice") and resolved_user is not None:
        from backend.bot.handlers.voice_query import handle_voice_query

        consumed = await handle_voice_query(db, message)
        if consumed:
            return resolved_user.id

    # Issue #603 — photo (or image document) = receipt OCR. Runs before
    # any text/wizard branches because photos carry no text payload,
    # and we want OCR to work regardless of wizard state so users can
    # snap a receipt anytime.
    if resolved_user is not None and (
        message.get("photo")
        or ((message.get("document") or {}).get("mime_type", "").startswith("image/"))
    ):
        from backend.bot.handlers.photo_receipt import handle_photo_message

        consumed = await handle_photo_message(db, message, resolved_user)
        if consumed:
            return resolved_user.id

    # Plain text during the onboarding name step must be consumed here —
    # otherwise the NL expense parser would try to parse the user's name
    # as a transaction.
    if (
        text
        and resolved_user is not None
        and not command.startswith("/")
        and resolved_user.onboarding_step == int(OnboardingStep.ASKING_NAME)
    ):
        consumed = await onboarding_handlers.handle_name_input(
            db, chat_id, resolved_user, text
        )
        if consumed:
            return resolved_user.id

    # Phase 4.1 — V2 onboarding first-asset text input. Same defensive
    # pattern as the legacy name step: catch the amount before the NL
    # expense parser interprets "200tr" as a transaction.
    if text and resolved_user is not None and not command.startswith("/"):
        from backend.bot.handlers import onboarding_v2 as onboarding_v2_handlers

        consumed = await onboarding_v2_handlers.handle_name_text_input(
            db, chat_id, resolved_user, text
        )
        if consumed:
            return resolved_user.id

        consumed = await onboarding_v2_handlers.handle_asset_text_input(
            db, chat_id, resolved_user, text
        )
        if consumed:
            return resolved_user.id

    # Profile edit text input — must run before generic wizard/free-form parsers.
    if (
        text
        and resolved_user is not None
        and not command.startswith("/")
        and (resolved_user.wizard_state or {}).get("flow")
        == profile_handlers.FLOW_PROFILE
    ):
        consumed = await profile_handlers.handle_profile_text_input(db, message)
        if consumed:
            return resolved_user.id

    # Feedback text input — must run before other wizard/free-form parsers.
    if (
        text
        and resolved_user is not None
        and not command.startswith("/")
        and (resolved_user.wizard_state or {}).get("flow")
        == feedback_handlers.FLOW_FEEDBACK
    ):
        consumed = await feedback_handlers.handle_feedback_text_input(db, message)
        if consumed:
            return resolved_user.id

    # Storytelling text input — runs before the asset wizard dispatch
    # because ``wizard_state`` is shared between flows; checking the
    # flow name keeps the two from stomping on each other.
    if (
        text
        and resolved_user is not None
        and not command.startswith("/")
        and (resolved_user.wizard_state or {}).get("flow")
        == storytelling_handlers.FLOW_STORYTELLING
    ):
        consumed = await storytelling_handlers.handle_storytelling_input(db, message)
        if consumed:
            return resolved_user.id

    # Asset-entry wizard mid-flow text input — must be consumed before
    # the NL expense parser tries to interpret "VCB 100 triệu" as a
    # transaction.
    if (
        text
        and resolved_user is not None
        and not command.startswith("/")
        and resolved_user.wizard_state
    ):
        consumed = await asset_entry_handlers.handle_asset_text_input(db, message)
        if consumed:
            return resolved_user.id

        # Phase 3.8 Epic 2 — income wizard mid-flow text. Same defensive
        # pattern as the asset wizard above: catch the text before the
        # NL expense parser claims it.
        consumed = await income_entry_handlers.handle_income_text_input(db, message)
        if consumed:
            return resolved_user.id

        # Phase 3.8 Epic 3 — recurring-pattern wizard mid-flow text.
        consumed = await recurring_entry_handlers.handle_recurring_text_input(
            db, message
        )
        if consumed:
            return resolved_user.id

        # Phase 3.8 Epic 5 — goals wizard mid-flow text.
        consumed = await goal_entry_handlers.handle_goals_text_input(db, message)
        if consumed:
            return resolved_user.id

        # Phase 4B Epic 2 — life-event wizard mid-flow text. Listens for
        # year / amount / duration replies while a life_event_* flow is
        # active so the user's "2028" doesn't reach the NL expense parser.
        consumed = await life_event_entry_handlers.handle_life_event_text_input(
            db, message
        )
        if consumed:
            return resolved_user.id

    # Natural-language message → NL expense parser / report intent / menu fallback.
    if text and resolved_user is not None and not command.startswith("/"):
        from backend.bot.handlers import onboarding_v2 as onboarding_v2_handlers

        await onboarding_v2_handlers.maybe_mark_query_next_action(
            db, chat_id, resolved_user
        )
    await handle_text_message(db, message)
    return resolved_user.id if resolved_user else None


async def _resolved_user_id_for_telegram(
    db: AsyncSession, telegram_id: int | None, dashboard_service
):
    if telegram_id is None:
        return None
    user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
    return user.id if user else None


async def _maybe_auto_exit_asset_wizard(
    db: AsyncSession,
    *,
    telegram_id: int | None,
    callback_data: str,
    dashboard_service,
) -> None:
    """Clear an active asset-entry wizard when the user taps a non-asset
    callback (menu / dashboard / briefing / transaction / follow-up).

    Button taps are a deliberate context switch — the user chose to
    navigate elsewhere. Leaving ``wizard_state`` in place would trap
    their next free-text message in the asset wizard's
    "👆 Bạn đang trong wizard thêm tài sản" nudge. Free-text input keeps
    the existing routing because text mid-wizard is most often the
    answer to a wizard prompt; only deliberate callback selections exit.

    Scope is intentionally narrow — only the asset-entry wizard
    (``asset_add_*`` flows). The storytelling confirm-pending step holds
    unsaved transactions in ``draft.pending`` and is resolved by its own
    ``story:*`` callbacks; the intent pending-action / awaiting-clarify
    state has its own 10-minute TTL. Auto-clearing either here would
    risk dropping in-flight user input.
    """
    # Phase 3.8 Epic 2 — generalised to also cover the income-stream
    # wizard (``income_*`` flows). Auto-exit fires only when the
    # callback belongs to a *different* wizard family than the one
    # currently active — taps within the same wizard's keyboard
    # (subtype, schedule pick) are always preserved.
    if not callback_data or telegram_id is None:
        return
    user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
    if user is None:
        return
    flow = (user.wizard_state or {}).get("flow") or ""

    is_asset_flow = flow.startswith("asset_add")
    is_income_flow = flow.startswith("income_")
    is_recurring_flow = flow.startswith("recurring_")
    is_goal_flow = flow.startswith("goal_")
    is_life_event_flow = flow.startswith("life_event")
    if not (
        is_asset_flow
        or is_income_flow
        or is_recurring_flow
        or is_goal_flow
        or is_life_event_flow
    ):
        return

    cb_belongs_to_asset = (
        callback_data.startswith("asset_add")
        or callback_data.startswith("asset_rental")
        or callback_data.startswith("dashboard:")
    )
    cb_belongs_to_income = callback_data.startswith("income")
    cb_belongs_to_recurring = callback_data.startswith(
        "recurring"
    ) or callback_data.startswith("reminder")
    cb_belongs_to_goal = callback_data.startswith("goals")
    cb_belongs_to_life_event = callback_data.startswith("life_event")
    if is_asset_flow and cb_belongs_to_asset:
        return
    if is_income_flow and cb_belongs_to_income:
        return
    if is_recurring_flow and cb_belongs_to_recurring:
        return
    if is_goal_flow and cb_belongs_to_goal:
        return
    if is_life_event_flow and cb_belongs_to_life_event:
        return

    from backend import analytics
    from backend.services import wizard_service

    if is_asset_flow:
        event = "asset_wizard_auto_exited"
    elif is_income_flow:
        event = "income_wizard_auto_exited"
    elif is_recurring_flow:
        event = "recurring_wizard_auto_exited"
    elif is_life_event_flow:
        event = "life_event_wizard_auto_exited"
    else:
        event = "goal_wizard_auto_exited"
    step = (user.wizard_state or {}).get("step")
    await wizard_service.clear(db, user.id)
    analytics.track(
        event,
        user_id=user.id,
        properties={
            "flow": flow,
            "step": step,
            "callback_data": callback_data,
        },
    )


async def _handle_callback(
    db: AsyncSession,
    callback_query: dict,
    *,
    about_handlers,
    onboarding_handlers,
    asset_entry_handlers,
    income_entry_handlers,
    recurring_entry_handlers,
    goal_entry_handlers,
    life_event_entry_handlers,
    briefing_handlers,
    storytelling_handlers,
    feedback_handlers,
    profile_handlers,
    positioning_survey_handlers,
    dashboard_service,
    handle_transaction_callback,
    handle_menu_v2_callback,
    answer_callback,
):
    """Dispatch a callback_query update. Returns the resolved internal
    user_id (or None) so ``route_update`` can stamp it on the
    telegram_updates row.
    """
    callback_data = callback_query.get("data", "")
    callback_id = callback_query["id"]
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")
    chat_id = (callback_query.get("message") or {}).get("chat", {}).get("id")
    if chat_id is not None and await _reject_if_suspended(
        db,
        telegram_id=telegram_id,
        chat_id=chat_id,
        dashboard_service=dashboard_service,
    ):
        return await _resolved_user_id_for_telegram(db, telegram_id, dashboard_service)

    async def _resolved_user_id():
        if telegram_id is None:
            return None
        user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
        return user.id if user else None

    # UX: tapping a non-asset_add callback while mid-wizard means the
    # user wants to switch context — exit the asset wizard so we don't
    # strand them in the "tap a button" nudge on their next message.
    await _maybe_auto_exit_asset_wizard(
        db,
        telegram_id=telegram_id,
        callback_data=callback_data,
        dashboard_service=dashboard_service,
    )

    # Phase 4.2 Epic 3 — Day 7 positioning survey callbacks.
    if await positioning_survey_handlers.handle_positioning_survey_callback(
        db, callback_query
    ):
        return await _resolved_user_id()

    # Feedback prompt callbacks own the feedback:* namespace.
    if await feedback_handlers.handle_feedback_callback(db, callback_query):
        return await _resolved_user_id()

    # Profile edit callbacks own the profile:* namespace.
    if await profile_handlers.handle_profile_callback(db, callback_query):
        return await _resolved_user_id()

    # About-page callbacks are static and do not need a user lookup.
    if await about_handlers.handle_about_callback(callback_query):
        return await _resolved_user_id()

    # Phase 4.1 — V2 onboarding callbacks own the ``onboarding_v2:*``
    # namespace. Must run before the legacy ``onboarding:*`` router so
    # the prefixes don't collide for users straddling versions.
    from backend.bot.handlers import onboarding_v2 as onboarding_v2_handlers

    if await onboarding_v2_handlers.handle_callback(db, callback_query):
        return await _resolved_user_id()

    # Onboarding callbacks first — otherwise the menu-callback handler
    # would swallow them.
    if await onboarding_handlers.handle_onboarding_callback(db, callback_query):
        return await _resolved_user_id()

    # Asset-entry wizard callbacks (asset_add:*).
    if await asset_entry_handlers.handle_asset_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.8 — mark-existing-as-rental callbacks (asset_rental:*).
    if await asset_entry_handlers.handle_asset_rental_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.9.5 — dashboard row edit callbacks (dashboard:edit:*).
    if await asset_entry_handlers.handle_dashboard_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.9.5 — asset manage/delete callbacks (asset_manage:*).
    if await asset_entry_handlers.handle_asset_manage_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.8 Epic 2 — income-stream wizard + list (income:*).
    if await income_entry_handlers.handle_income_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.8 Epic 3 — recurring patterns + reminder actions
    # (recurring:* and reminder:*).
    if await recurring_entry_handlers.handle_recurring_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.8 Epic 5 — goals wizard + list (goals:*).
    if await goal_entry_handlers.handle_goals_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 4B Epic 2 — life-event wizard + menu (life_event:*).
    if await life_event_entry_handlers.handle_life_event_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 4.1 Story A.8 — first-briefing "what is this?" button.
    callback_data_raw = callback_query.get("data") or ""
    if callback_data_raw.startswith("first_briefing:"):
        from backend.bot.handlers.briefing_first_briefing import (
            handle_first_briefing_callback,
        )

        if await handle_first_briefing_callback(db, callback_query):
            return await _resolved_user_id()

    # Phase 4.3 Story 3.1-3.6 — Twin habit-loop callbacks own the
    # ``twin:causality``, ``twin:action``, ``twin:action_done:*`` and
    # ``action_suggestion:dismiss:*`` namespaces fired from on-demand
    # recompute notifications. Distinct from the menu router which owns
    # ``menu:twin:*`` (category=twin under the menu prefix).
    if callback_data == "twin:causality" or callback_data == "twin:action" or callback_data.startswith("twin:action_done:"):
        from backend.bot.handlers.twin_callback_handler import handle_twin_callback

        if await handle_twin_callback(db, callback_query):
            return await _resolved_user_id()

    if callback_data.startswith("action_suggestion:dismiss:"):
        from backend.bot.handlers.twin_callback_handler import (
            handle_action_suggestion_callback,
        )

        if await handle_action_suggestion_callback(db, callback_query):
            return await _resolved_user_id()

    # Phase 4.2 Epic 2 — Next Best Action shortcut buttons.
    from backend.bot.handlers import onboarding_v2 as onboarding_v2_handlers

    if await onboarding_v2_handlers.handle_next_action_callback(db, callback_query):
        return await _resolved_user_id()

    # Morning-briefing button taps (briefing:*). Handled before the
    # transaction router because the briefing keyboard sits on its own
    # message thread and never overlaps with transaction prefixes.
    if await briefing_handlers.handle_briefing_callback(db, callback_query):
        return await _resolved_user_id()

    # Storytelling confirmation taps (story:*). Routed before the
    # transaction router so the "story:" prefix doesn't collide with
    # generic per-transaction edit/delete callbacks.
    if await storytelling_handlers.handle_storytelling_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.5 intent callbacks (intent_confirm:*, intent_clarify:*,
    # followup:*). Routed before the transaction handler because
    # those prefixes are distinct and the user is mid-flow.
    if callback_data.startswith("intent_") or callback_data.startswith("followup:"):
        from backend.bot.handlers.message import handle_intent_callback

        await answer_callback(callback_id)
        if await handle_intent_callback(db, callback_query):
            return await _resolved_user_id()

    # Transaction callbacks handle their own answerCallbackQuery so users
    # get richer feedback.
    if await handle_transaction_callback(db, callback_query):
        return await _resolved_user_id()

    # Phase 3.6 menu callbacks own the entire ``menu:*`` namespace —
    # main / category / action callbacks render the new UX, legacy V1
    # prefixes (``menu:gmail_scan`` etc.) get a graceful "menu has been
    # upgraded" redirect.
    if await handle_menu_v2_callback(db, callback_query):
        return await _resolved_user_id()

    # No handler matched — acknowledge so the user's spinner clears.
    await answer_callback(callback_id)
    return await _resolved_user_id()


async def process_update_safely(update_id: int, data: dict) -> None:
    """Background-task wrapper — never raises.

    Marks the ``telegram_updates`` row as ``done`` on success, ``failed``
    on exception. Logs but swallows so a handler bug cannot kill the
    event loop or propagate to Telegram as a webhook error.
    """
    try:
        await route_update(data)
        await _mark_status(update_id, STATUS_DONE)
    except Exception as exc:  # noqa: BLE001 — we explicitly want to swallow.
        logger.exception("route_update failed: update_id=%s", update_id)
        await _mark_status(update_id, STATUS_FAILED, error=str(exc)[:2000])


async def _mark_status(
    update_id: int, status: str, *, error: str | None = None
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            await db.execute(
                sa_update(TelegramUpdate)
                .where(TelegramUpdate.update_id == update_id)
                .values(
                    status=status,
                    processed_at=datetime.utcnow(),
                    error_message=error,
                )
            )
            await db.commit()
        except Exception:
            # Status update is best-effort — don't mask the real error
            # (if any) the caller is trying to report.
            logger.exception("Failed to mark update_id=%s as %s", update_id, status)
            await db.rollback()


async def _claim_orphan(db: AsyncSession, update_id: int, cutoff: datetime) -> bool:
    """Atomically claim one stale 'processing' row for this worker.

    Bumps ``received_at`` to NOW() only if the row is still ``status
    = 'processing'`` AND older than ``cutoff``. The row-level lock
    taken during UPDATE serializes concurrent workers — only the first
    worker's UPDATE hits (rowcount 1), the rest see received_at
    already past the cutoff and their predicate fails (rowcount 0).

    Returns True if this worker claimed the row and should schedule
    processing, False if another worker got there first.
    """
    stmt = (
        sa_update(TelegramUpdate)
        .where(
            TelegramUpdate.update_id == update_id,
            TelegramUpdate.status == STATUS_PROCESSING,
            TelegramUpdate.received_at < cutoff,
        )
        .values(received_at=datetime.utcnow())
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount == 1


async def recover_orphaned_updates() -> int:
    """Re-enqueue updates stuck in ``processing`` from a prior run.

    Runs both at startup and on a recurring timer (see
    ``run_recovery_loop``) so rows that get stuck after the web server
    is already up — e.g. a worker OOMs mid-handler — still get picked
    up without waiting for the next deploy.

    Safe across multiple uvicorn workers: each candidate is atomically
    claimed via ``_claim_orphan`` before being scheduled, so exactly
    one worker dispatches each orphan. Caps the batch per pass to
    avoid thundering-herd scheduling after a long outage. Returns the
    number of tasks spawned.
    """
    cutoff = datetime.utcnow() - ORPHAN_CUTOFF
    session_factory = get_session_factory()

    spawned = 0
    async with session_factory() as db:
        stmt = (
            select(TelegramUpdate.update_id, TelegramUpdate.payload)
            .where(
                TelegramUpdate.status == STATUS_PROCESSING,
                TelegramUpdate.received_at < cutoff,
            )
            .order_by(TelegramUpdate.received_at.asc())
            .limit(ORPHAN_BATCH_LIMIT)
        )
        candidates = (await db.execute(stmt)).all()

        for update_id, payload in candidates:
            if await _claim_orphan(db, update_id, cutoff):
                asyncio.create_task(process_update_safely(update_id, payload))
                spawned += 1

    if spawned:
        logger.info(
            "Recovered %d orphaned Telegram update(s) (%d candidates inspected)",
            spawned,
            len(candidates),
        )
    return spawned


# How often the in-process recovery loop wakes up. Must be shorter than
# ORPHAN_CUTOFF so a freshly-stuck row is picked up within one cutoff
# window regardless of when it became stale. 2 min gives ~2.5x headroom.
RECOVERY_INTERVAL = 120  # seconds


async def run_recovery_loop(interval_seconds: int = RECOVERY_INTERVAL) -> None:
    """Long-running coroutine that periodically re-enqueues orphans.

    Started from the FastAPI lifespan. Exits cleanly on
    ``CancelledError`` (raised during shutdown). Any other exception is
    logged and the loop continues — recovery is advisory, a single bad
    pass shouldn't kill it.
    """
    logger.info("Orphan recovery loop started (interval=%ss)", interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await recover_orphaned_updates()
            except Exception:
                logger.exception("Orphan recovery pass failed; continuing loop")
    except asyncio.CancelledError:
        logger.info("Orphan recovery loop cancelled")
        raise
