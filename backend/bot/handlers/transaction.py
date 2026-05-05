"""Sending transaction confirmation messages with inline action buttons.

Used after the backend creates a new expense (e.g. from manual ingestion,
OCR confirm, or SMS parsing) to display a rich confirmation in Telegram.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.templates import format_transaction_confirmation
from backend.bot.keyboards.transaction_keyboard import transaction_actions_keyboard
from backend.models.expense import Expense
from backend.services.dashboard_service import get_user_by_id
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


async def send_transaction_confirmation(
    db: AsyncSession,
    expense: Expense,
    *,
    daily_spent: float | None = None,
    daily_budget: float | None = None,
) -> None:
    """Gửi tin nhắn xác nhận + inline keyboard cho user owning this expense."""
    user = await get_user_by_id(db, expense.user_id)
    if not user or not user.telegram_id:
        return

    text = format_transaction_confirmation(
        merchant=expense.merchant or expense.note or "Giao dịch",
        amount=float(expense.amount),
        category_code=_normalize_category(expense.category),
        time=expense.created_at,
        daily_spent=daily_spent,
        daily_budget=daily_budget,
    )
    keyboard = transaction_actions_keyboard(str(expense.id))
    await send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
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
        logging.getLogger(__name__).warning(
            "step_5_aha_moment failed", exc_info=True
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
