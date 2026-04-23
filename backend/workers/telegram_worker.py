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

See docs/strategy/scaling-refactor-A.md §A3 + §A1 for context.
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


async def route_update(data: dict) -> None:
    """Dispatch one Telegram update to the right handler.

    Opens a fresh ``AsyncSession`` — the webhook's session is long gone
    by the time this runs in a background task. Commits on success,
    rolls back on exception (the caller marks the row status).
    """
    # Imports are local to avoid a module-import cycle with routers/
    # and to keep worker startup cheap (handlers pull in Telegram SDK
    # HTTP clients which open sockets on import).
    from backend.bot.handlers import onboarding as onboarding_handlers
    from backend.bot.handlers.callbacks import handle_transaction_callback
    from backend.bot.handlers.message import (
        handle_report_callback,
        handle_report_command,
        handle_text_message,
    )
    from backend.bot.personality.onboarding_flow import OnboardingStep
    from backend.services import dashboard_service
    from backend.services.telegram_service import (
        answer_callback,
        handle_menu_callback,
        send_menu,
    )
    from backend import analytics

    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            message = data.get("message")
            if message:
                await _handle_message(
                    db, message,
                    onboarding_handlers=onboarding_handlers,
                    dashboard_service=dashboard_service,
                    handle_report_command=handle_report_command,
                    handle_text_message=handle_text_message,
                    send_menu=send_menu,
                    OnboardingStep=OnboardingStep,
                    analytics=analytics,
                )
            else:
                callback_query = data.get("callback_query")
                if callback_query:
                    await _handle_callback(
                        db, callback_query,
                        onboarding_handlers=onboarding_handlers,
                        handle_transaction_callback=handle_transaction_callback,
                        handle_report_callback=handle_report_callback,
                        handle_menu_callback=handle_menu_callback,
                        answer_callback=answer_callback,
                    )
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def _handle_message(
    db: AsyncSession,
    message: dict,
    *,
    onboarding_handlers,
    dashboard_service,
    handle_report_command,
    handle_text_message,
    send_menu,
    OnboardingStep,
    analytics,
) -> None:
    text = message.get("text", "")
    chat_id = message["chat"]["id"]
    command = text.strip().lower()
    from_user = message.get("from") or {}
    telegram_id = from_user.get("id")

    if command == "/start":
        if telegram_id is None:
            analytics.track(
                analytics.EventType.BOT_STARTED,
                properties={"has_telegram_id": False, "new_user": False},
            )
            return

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
        await onboarding_handlers.resume_or_start(db, chat_id, user)
        return

    if command in ("/menu", "menu"):
        await send_menu(chat_id)
        return

    if command == "/report":
        await handle_report_command(db, message)
        return

    # Plain text during the onboarding name step must be consumed here —
    # otherwise the NL expense parser would try to parse the user's name
    # as a transaction.
    if text and telegram_id is not None and not command.startswith("/"):
        user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
        if user and user.onboarding_step == int(OnboardingStep.ASKING_NAME):
            consumed = await onboarding_handlers.handle_name_input(
                db, chat_id, user, text
            )
            if consumed:
                return

    # Natural-language message → NL expense parser / report intent / menu fallback.
    await handle_text_message(db, message)


async def _handle_callback(
    db: AsyncSession,
    callback_query: dict,
    *,
    onboarding_handlers,
    handle_transaction_callback,
    handle_report_callback,
    handle_menu_callback,
    answer_callback,
) -> None:
    callback_data = callback_query.get("data", "")
    chat_id = callback_query["message"]["chat"]["id"]
    callback_id = callback_query["id"]

    # Onboarding callbacks first — otherwise the menu-callback handler
    # would swallow them.
    if await onboarding_handlers.handle_onboarding_callback(db, callback_query):
        return

    # Transaction callbacks handle their own answerCallbackQuery so users
    # get richer feedback.
    if await handle_transaction_callback(db, callback_query):
        return

    await answer_callback(callback_id)

    # "Báo cáo" button → generate report immediately instead of showing help.
    if callback_data == "menu:report":
        await handle_report_callback(db, callback_query)
        return

    await handle_menu_callback(chat_id, callback_data)


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


async def recover_orphaned_updates() -> int:
    """Re-enqueue updates stuck in ``processing`` from a prior run.

    Called from the FastAPI lifespan startup hook. Caps the batch so a
    long outage doesn't produce a thundering herd on restart. Returns
    the number of tasks spawned.
    """
    cutoff = datetime.utcnow() - ORPHAN_CUTOFF
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = (
            select(TelegramUpdate)
            .where(
                TelegramUpdate.status == STATUS_PROCESSING,
                TelegramUpdate.received_at < cutoff,
            )
            .order_by(TelegramUpdate.received_at.asc())
            .limit(ORPHAN_BATCH_LIMIT)
        )
        orphans = (await db.execute(stmt)).scalars().all()

    for orphan in orphans:
        asyncio.create_task(process_update_safely(orphan.update_id, orphan.payload))

    if orphans:
        logger.info("Recovered %d orphaned Telegram updates", len(orphans))
    return len(orphans)
