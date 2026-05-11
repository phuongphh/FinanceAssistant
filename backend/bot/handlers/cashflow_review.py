"""Telegram callback handler for Phase 4B cashflow pattern review (S15).

Handles inline button taps from the pattern review messages sent by
``cashflow_detection_job``. Three outcomes per pattern:

- ``cashflow:confirm:<pattern_uuid>``  → is_confirmed = True
  → pattern feeds into 3-month forecast from next daily run
- ``cashflow:dismiss:<pattern_uuid>``  → dismissed_until = now + 30d
  → pattern will not appear in review again for 30 days
- ``cashflow:edit:<pattern_uuid>``     → prompt user for corrected amount,
  then confirm automatically once they enter a valid number

Layer contract:
- Handler reads Telegram data, calls service, formats response.
- No db.commit() here — committed by the worker that called us.
- No direct telegram_service imports — uses get_notifier() port.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.keyboards.common import parse_callback
from backend.models.recurring_pattern import RecurringPattern
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    answer_callback,
    edit_message_text,
    send_message,
)

logger = logging.getLogger(__name__)

CB_CASHFLOW = "cashflow"
DISMISS_DAYS = 30


async def handle_cashflow_callback(
    db: AsyncSession,
    callback_query: dict[str, Any],
) -> bool:
    """Route cashflow: callbacks. Returns True if handled."""
    data = callback_query.get("data", "")
    if not data.startswith(CB_CASHFLOW + ":"):
        return False

    parts = parse_callback(data)
    if len(parts) < 2:
        return False

    action = parts[1]
    pattern_uuid_str = parts[2] if len(parts) > 2 else None

    from_user = callback_query.get("from", {})
    telegram_id = from_user.get("id")
    callback_id = callback_query.get("id", "")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(callback_id, text="Không tìm thấy người dùng.")
        return True

    if action == "confirm":
        await _handle_confirm(db, callback_id, chat_id, message_id, pattern_uuid_str)
    elif action == "dismiss":
        await _handle_dismiss(db, callback_id, chat_id, message_id, pattern_uuid_str)
    elif action == "edit":
        await _handle_edit_prompt(db, user, callback_id, chat_id, pattern_uuid_str)
    else:
        await answer_callback(callback_id, text="Hành động không hợp lệ.")

    return True


# ── Action handlers ──────────────────────────────────────────────────────────


async def _handle_confirm(
    db: AsyncSession,
    callback_id: str,
    chat_id: int,
    message_id: int,
    pattern_uuid_str: str | None,
) -> None:
    pattern = await _load_pattern(db, pattern_uuid_str)
    if pattern is None:
        await answer_callback(callback_id, text="Không tìm thấy khoản định kỳ.")
        return

    pattern.user_confirmed = True
    pattern.enable_reminders = True
    db.add(pattern)
    await db.flush()

    await answer_callback(callback_id, text="✅ Đã xác nhận!")
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            f"✅ <b>{pattern.description or pattern.name}</b>\n"
            "Đã xác nhận — Bé Tiền sẽ dùng khoản này trong dự báo cashflow."
        ),
        parse_mode="HTML",
        reply_markup=None,
    )
    logger.info("cashflow review: confirmed pattern=%s", pattern.id)


async def _handle_dismiss(
    db: AsyncSession,
    callback_id: str,
    chat_id: int,
    message_id: int,
    pattern_uuid_str: str | None,
) -> None:
    pattern = await _load_pattern(db, pattern_uuid_str)
    if pattern is None:
        await answer_callback(callback_id, text="Không tìm thấy khoản định kỳ.")
        return

    pattern.dismissed_until = datetime.now(timezone.utc) + timedelta(days=DISMISS_DAYS)
    db.add(pattern)
    await db.flush()

    await answer_callback(callback_id, text="Đã bỏ qua trong 30 ngày.")
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            f"❌ Đã bỏ qua <b>{pattern.description or pattern.name}</b> trong 30 ngày.\n"
            "Bé Tiền sẽ không hỏi lại trong thời gian này."
        ),
        parse_mode="HTML",
        reply_markup=None,
    )
    logger.info("cashflow review: dismissed pattern=%s for 30d", pattern.id)


async def _handle_edit_prompt(
    db: AsyncSession,
    user: Any,
    callback_id: str,
    chat_id: int,
    pattern_uuid_str: str | None,
) -> None:
    pattern = await _load_pattern(db, pattern_uuid_str)
    if pattern is None:
        await answer_callback(callback_id, text="Không tìm thấy khoản định kỳ.")
        return

    await answer_callback(callback_id)

    from backend.bot.formatters.money import format_money_short
    current_amt = format_money_short(Decimal(str(pattern.expected_amount)))

    # Store edit state in user wizard_state so the next free-form text
    # message is interpreted as the corrected amount.
    user.wizard_state = {
        "flow": "cashflow_pattern_edit",
        "step": "amount",
        "draft": {"pattern_id": str(pattern.id)},
    }
    db.add(user)
    await db.flush()

    await send_message(
        chat_id=chat_id,
        text=(
            f"Nhập số tiền đúng cho khoản <b>{pattern.description or pattern.name}</b>.\n"
            f"Hiện tại: <b>{current_amt}</b>\n\n"
            "Ví dụ: <code>8000000</code> hoặc <code>8tr</code>"
        ),
        parse_mode="HTML",
    )


async def handle_cashflow_edit_amount(
    db: AsyncSession,
    user: Any,
    text: str,
) -> bool:
    """Called from free-form text handler when wizard_state.flow == cashflow_pattern_edit.

    Returns True if the wizard consumed this message (caller should not
    process further).
    """
    state = getattr(user, "wizard_state", None) or {}
    if state.get("flow") != "cashflow_pattern_edit":
        return False

    draft = state.get("draft", {})
    pattern_id_str = draft.get("pattern_id")
    if not pattern_id_str:
        return False

    pattern = await _load_pattern(db, pattern_id_str)
    if pattern is None:
        return False

    try:
        amount = _parse_amount(text.strip())
    except ValueError:
        await send_message(
            chat_id=user.telegram_id,
            text="Số tiền không hợp lệ. Vui lòng nhập lại (ví dụ: 8000000 hoặc 8tr).",
        )
        return True

    pattern.expected_amount = amount
    pattern.user_confirmed = True
    pattern.enable_reminders = True
    user.wizard_state = None
    db.add(pattern)
    db.add(user)
    await db.flush()

    from backend.bot.formatters.money import format_money_short
    await send_message(
        chat_id=user.telegram_id,
        text=(
            f"✅ Đã cập nhật và xác nhận: "
            f"<b>{pattern.description or pattern.name}</b> — "
            f"{format_money_short(amount)}/tháng.\n"
            "Bé Tiền sẽ dùng con số này trong dự báo cashflow."
        ),
        parse_mode="HTML",
    )
    logger.info(
        "cashflow review: edited+confirmed pattern=%s amount=%s", pattern.id, amount
    )
    return True


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _load_pattern(
    db: AsyncSession, pattern_uuid_str: str | None,
) -> RecurringPattern | None:
    if not pattern_uuid_str:
        return None
    try:
        pid = uuid.UUID(pattern_uuid_str)
    except ValueError:
        return None
    stmt = select(RecurringPattern).where(RecurringPattern.id == pid)
    return (await db.execute(stmt)).scalars().first()


def _parse_amount(text: str) -> Decimal:
    """Parse Vietnamese amount strings: '8tr' → 8_000_000, '500k' → 500_000."""
    t = text.lower().replace(",", "").replace(".", "").strip()
    multiplier = Decimal(1)
    if t.endswith("tr"):
        multiplier = Decimal(1_000_000)
        t = t[:-2]
    elif t.endswith("k"):
        multiplier = Decimal(1_000)
        t = t[:-1]
    elif t.endswith("m"):
        multiplier = Decimal(1_000_000)
        t = t[:-1]
    try:
        return Decimal(t) * multiplier
    except InvalidOperation:
        raise ValueError(f"Cannot parse amount: {text!r}")
