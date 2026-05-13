"""22:00 ICT daily transaction summary for expense + money-in rows."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.config import get_settings
from backend.database import get_session_factory
from backend.models.expense import Expense
from backend.models.user import User
from backend.ports.notifier import get_notifier

logger = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _money_short(amount: float) -> str:
    amount = float(amount or 0)
    abs_amount = abs(amount)
    if abs_amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}".rstrip("0").rstrip(".") + "tr"
    if abs_amount >= 1_000:
        return f"{round(amount / 1_000)}k"
    return f"{round(amount)}đ"


def format_daily_transaction_summary(items: list[Expense]) -> str:
    lines = ["📒 Tổng kết giao dịch hôm nay"]
    money_in = 0.0
    money_out = 0.0
    for item in items:
        tx_type = getattr(item, "transaction_type", "expense") or "expense"
        sign = "+" if tx_type == "money_in" else "-"
        if tx_type == "money_in":
            money_in += float(item.amount or 0)
        else:
            money_out += float(item.amount or 0)
        label = item.merchant or item.note or "Giao dịch"
        lines.append(f"{sign}{_money_short(float(item.amount or 0))} {label}")
    lines.append("")
    lines.append(
        f"Hôm nay: +{_money_short(money_in)} vào, -{_money_short(money_out)} ra"
    )
    return "\n".join(lines)


async def run_daily_transaction_summary(*, now: datetime | None = None) -> int:
    if not get_settings().daily_transaction_summary_enabled:
        logger.info("daily-transaction-summary: disabled")
        return 0

    now = now or datetime.now(TZ)
    today = now.date()
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = (
            select(User, Expense)
            .join(Expense, Expense.user_id == User.id)
            .where(
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.telegram_id.isnot(None),
                Expense.expense_date == today,
                Expense.deleted_at.is_(None),
            )
            .order_by(User.id.asc(), Expense.created_at.asc())
        )
        rows = (await db.execute(stmt)).all()

    grouped: dict[User, list[Expense]] = defaultdict(list)
    for user, expense in rows:
        grouped[user].append(expense)

    notifier = get_notifier()
    sent = 0
    for user, items in grouped.items():
        if not items:
            continue
        result = await notifier.send_message(
            chat_id=user.telegram_id,
            text=format_daily_transaction_summary(items),
            parse_mode=None,
        )
        if result is not None:
            sent += 1
    logger.info("daily-transaction-summary: sent=%d at %s", sent, time(22, 0))
    return sent
