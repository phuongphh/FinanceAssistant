"""Sending transaction confirmation messages with inline action buttons.

Used after the backend creates a new expense (e.g. from manual ingestion,
OCR confirm, or SMS parsing) to display a rich confirmation.

Channel routing (Phase 5.0 #2.4)
--------------------------------
Both senders here are called by ``action_quick_transaction``, which sends
its own reply and then returns an empty string to the dispatcher. That
made them Telegram-only by construction: a Zalo user's transaction was
recorded and the channel stayed silent, because the only exit path led to
``send_message(chat_id=user.telegram_id, ...)``.

Rather than thread a ``channel`` argument through pipeline → dispatcher →
handler for the benefit of the handlers that self-send, the channel is
read from :mod:`backend.bot.channel_context`, which the Zalo worker sets
once at its task boundary. The contextvar defaults to Telegram, so every
pre-existing caller — schedulers, the Telegram worker, OCR confirm, admin
scripts — produces byte-identical output to before.

The Zalo branch deliberately skips two Telegram-only affordances: the
inline keyboard (Zalo OA has none in 5.0) and the onboarding aha-moment
follow-up (onboarding lives entirely in Telegram).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot import channel_context
from backend.bot.formatters.templates import (
    format_transaction_batch_confirmation,
    format_transaction_confirmation,
)
from backend.bot.formatters.zalo_transaction import (
    format_zalo_transaction,
    format_zalo_transaction_batch,
)
from backend.bot.keyboards.transaction_keyboard import (
    transaction_actions_keyboard,
    transaction_batch_actions_keyboard,
)
from backend.bot.utils.emoji_animation import message_kwargs_for_animation
from backend.models.expense import Expense
from backend.models.user import User
from backend.services.dashboard_service import get_user_by_id
from backend.services.expense_source_resolver import (
    resolve_source_label_for_expense,
)
from backend.services.telegram_service import send_message

# Legacy category codes (from earlier phases) → new shared codes.
_LEGACY_CATEGORY_ALIASES = {
    "food_drink": "food",
    "utilities": "utility",
    "savings": "saving",
    "other": "other",
    "needs_review": "other",
}


def _normalize_category(code: str | None) -> str:
    if not code:
        return "other"
    return _LEGACY_CATEGORY_ALIASES.get(code, code)


async def _send_on_zalo(user: User, text: str) -> bool:
    """Deliver ``text`` to ``user``'s linked Zalo account.

    Returns whether the message actually reached Zalo. ``False`` covers
    three states, all of them real rather than exceptional:

    * this user has no Zalo side — no ``zalo_user_id``, or the OA
      credentials aren't configured on this server (a dev box);
    * the 48h reply window is shut or the eight free consulting messages
      are spent, so the notifier declined to call ``/message/cs``;
    * the OA call itself failed after the client's own retries.

    Each one means the caller should fall through to Telegram, which is
    exactly what it does — the DoD for the window ceiling is *"Telegram
    vẫn nhận"*, not silence.

    Imported inside the function: the Zalo adapter pulls in the OA client
    and its settings, and this module is imported by the Telegram hot
    path on every startup, flag on or off.
    """
    if not user.zalo_user_id or not text:
        return False

    from backend.adapters.zalo_oa import get_zalo_oa_client
    from backend.adapters.zalo_window_notifier import build_zalo_notifier

    client = get_zalo_oa_client()
    if not client.is_configured:
        return False

    # chat_id is unused by the Zalo notifier — the recipient is bound at
    # construction — but the Notifier port requires the positional arg.
    notifier = build_zalo_notifier(user.zalo_user_id, client=client)
    return await notifier.send_message(0, text) is not None


async def send_transaction_confirmation(
    db: AsyncSession,
    expense: Expense,
    *,
    daily_spent: float | None = None,
    daily_budget: float | None = None,
) -> None:
    """Gửi tin nhắn xác nhận + inline keyboard cho user owning this expense."""
    user = await get_user_by_id(db, expense.user_id)
    if not user:
        return

    # Both expense and money-in get the rich card: source label + 4 edit
    # buttons + edit hint. Daily budget context stays expense-only.
    tx_type = expense.transaction_type or "expense"
    is_card_type = tx_type in ("expense", "money_in")
    is_expense = tx_type == "expense"
    source_label = (
        await resolve_source_label_for_expense(db, expense) if is_card_type else None
    )

    if channel_context.is_zalo():
        # The edit hint points at Telegram, so only offer it to users who
        # have a Telegram side to go to.
        sent = await _send_on_zalo(
            user,
            format_zalo_transaction(
                merchant=expense.merchant or expense.note,
                amount=expense.amount,
                category_code=_normalize_category(expense.category),
                transaction_type=tx_type,
                expense_date=expense.expense_date,
                source_label=source_label,
                show_edit_hint=is_card_type and bool(user.telegram_id),
            ),
        )
        if sent:
            return
        # Unreachable on Zalo — fall through so a linked Telegram user
        # still gets their confirmation rather than none at all.

    if not user.telegram_id:
        return

    text = format_transaction_confirmation(
        merchant=expense.merchant or expense.note or "Giao dịch",
        amount=float(expense.amount),
        category_code=_normalize_category(expense.category),
        time=expense.created_at,
        daily_spent=daily_spent if is_expense else None,
        daily_budget=daily_budget if is_expense else None,
        source_label=source_label,
        show_edit_hint=is_card_type,
        transaction_type=tx_type,
        expense_date=expense.expense_date,
    )
    reply_markup = transaction_actions_keyboard(str(expense.id))
    await send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        **message_kwargs_for_animation(text, "transaction"),
    )

    # Onboarding hook: if this is the user's first transaction during
    # the onboarding flow, follow the confirmation with the aha-moment
    # message. Imported locally to avoid a circular import via
    # personality → services → handlers.
    from backend.bot.handlers.onboarding import step_5_aha_moment
    from backend.services import onboarding_service as _onb

    try:
        if await _onb.is_in_first_transaction_step(db, user.id):
            await step_5_aha_moment(db, user.telegram_id, user)
    except Exception:
        # Aha-moment is decorative — never block a confirmed transaction.
        import logging

        logging.getLogger(__name__).warning("step_5_aha_moment failed", exc_info=True)


async def send_transaction_batch_confirmation(
    db: AsyncSession,
    expenses: list[Expense],
    *,
    batch_id: str,
) -> None:
    """Gửi một confirmation chung cho nhiều expense vừa tạo."""
    if not expenses:
        return

    user = await get_user_by_id(db, expenses[0].user_id)
    if not user:
        return

    all_expense = all(e.transaction_type == "expense" for e in expenses)
    # Pick the most common source label across the batch — if every item
    # was charged to the same source, show it; otherwise omit (mixed batches
    # are rare and we'd rather under-show than mislead).
    source_label: str | None = None
    if all_expense:
        labels = [await resolve_source_label_for_expense(db, e) for e in expenses]
        unique = {label for label in labels if label}
        if len(unique) == 1 and len(labels) == len(expenses):
            source_label = next(iter(unique))

    # Batch items can technically be on different days (rare — usually a
    # single ``ngày dd/mm`` covers the whole message); only surface the
    # date row when every item agrees AND it isn't today.
    batch_dates = {expense.expense_date for expense in expenses}
    batch_date = batch_dates.pop() if len(batch_dates) == 1 else None

    if channel_context.is_zalo():
        sent = await _send_on_zalo(
            user,
            format_zalo_transaction_batch(
                items=[
                    (
                        expense.merchant or expense.note,
                        expense.amount,
                        _normalize_category(expense.category),
                    )
                    for expense in expenses
                ],
                expense_date=batch_date,
                source_label=source_label,
                show_edit_hint=all_expense and bool(user.telegram_id),
            ),
        )
        if sent:
            return

    if not user.telegram_id:
        return

    text = format_transaction_batch_confirmation(
        items=[
            (
                expense.merchant or expense.note or "Giao dịch",
                float(expense.amount),
                _normalize_category(expense.category),
            )
            for expense in expenses
        ],
        time=max((expense.created_at for expense in expenses), default=None),
        source_label=source_label,
        show_edit_hint=all_expense,
        expense_date=batch_date,
    )
    reply_markup = None if all_expense else transaction_batch_actions_keyboard(batch_id)
    await send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        **message_kwargs_for_animation(text, "transaction"),
    )


async def resolve_transaction_by_callback_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    callback_id: str,
) -> Expense | None:
    """Lấy expense từ id nằm trong callback_data.

    Hỗ trợ cả full UUID (ưu tiên) lẫn id rút gọn (prefix match) nếu cần
    mở rộng sau.
    """
    try:
        expense_id = uuid.UUID(callback_id)
    except ValueError:
        return None

    stmt = select(Expense).where(
        Expense.id == expense_id,
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def resolve_transactions_by_batch_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    batch_id: str,
) -> list[Expense]:
    """Lấy các expense thuộc cùng một batch manual input."""
    stmt = (
        select(Expense)
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
            Expense.raw_data["batch_id"].as_string() == batch_id,
        )
        .order_by(Expense.created_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())
