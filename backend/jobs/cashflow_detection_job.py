"""Phase 4B S14 — Weekly recurring pattern detection cron job.

Schedule: Monday 06:00 Asia/Ho_Chi_Minh.

Per-user pipeline:
1. Run ``cashflow.detector.detect_and_upsert`` (new unconfirmed patterns).
2. Query unconfirmed patterns pending review (max 5).
3. Send one Telegram review message per pending pattern with
   confirm/dismiss/edit buttons.

Rate guard: 30-second sleep between users to stay within Telegram limits
during the weekly batch.

Only runs for users with ≥ 90 days of transaction history (same as the
Phase 3.8 detector — avoids false positives on new accounts).

Layer contract:
- Job owns the session + commit boundary.
- cashflow.detector flushes but does not commit.
- send_message is called after db.commit() so a failed send does not
  roll back the pattern rows (idempotent — re-running detection won't
  duplicate rows due to fingerprint dedup in the detector).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import and_, select

from backend.bot.keyboards.cashflow_keyboard import pattern_review_keyboard
from backend.database import get_session_factory
from backend.models.user import User
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

MIN_HISTORY_DAYS = 90
INTER_USER_SLEEP = 1.0     # seconds — Telegram rate limit headroom
_CONTENT_PATH = Path(__file__).resolve().parents[2] / "content" / "cashflow.yaml"


async def run_cashflow_detection() -> None:
    """Entry point for APScheduler registration."""
    from backend.cashflow.detector import detect_and_upsert

    session_factory = get_session_factory()
    async with session_factory() as db:
        users = await _eligible_users(db)

    logger.info("cashflow detection: %d eligible users", len(users))

    for user in users:
        async with session_factory() as db:
            try:
                await detect_and_upsert(db, user.id)
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("cashflow detection failed for user %s", user.id)

        # Send review messages in a separate read session (after commit
        # so the upserted rows are visible).
        async with session_factory() as db:
            try:
                await _send_review_messages(db, user)
            except Exception:
                logger.exception(
                    "cashflow review message failed for user %s", user.id
                )

        await asyncio.sleep(INTER_USER_SLEEP)


async def _send_review_messages(db, user: User) -> None:
    from backend.cashflow.detector import load_unconfirmed_pending

    pending = await load_unconfirmed_pending(db, user.id)
    if not pending:
        return

    copy = _load_copy().get("pattern_review", {})
    income_emoji = copy.get("income_emoji", "💰")
    expense_emoji = copy.get("expense_emoji", "💸")
    pattern_line_tpl = copy.get("pattern_line", "{idx}. {description}")

    for idx, pattern in enumerate(pending, start=1):
        type_emoji = (
            income_emoji
            if pattern.pattern_type == "income"
            else expense_emoji
        )
        from backend.bot.formatters.money import format_money_short
        from decimal import Decimal

        line = pattern_line_tpl.format(
            idx=idx,
            type_emoji=type_emoji,
            description=pattern.description or pattern.name,
            amount=format_money_short(Decimal(str(pattern.expected_amount))),
            day=pattern.expected_day_of_month or "?",
        )
        await send_message(
            chat_id=user.telegram_id,
            text=(
                f"💡 Bé Tiền nhận ra khoản định kỳ:\n\n{line}\n\n"
                "Xác nhận để Bé Tiền dùng vào dự báo cashflow nhé?"
            ),
            parse_mode="HTML",
            reply_markup=pattern_review_keyboard(pattern.id),
        )
        await asyncio.sleep(0.5)  # 500ms between messages per user


async def _eligible_users(db) -> list[User]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MIN_HISTORY_DAYS)
    stmt = select(User).where(
        and_(
            User.created_at <= cutoff,
            User.deleted_at.is_(None),
            User.telegram_id.isnot(None),
            User.is_active.is_(True),
        )
    )
    return list((await db.execute(stmt)).scalars().all())


@lru_cache(maxsize=1)
def _load_copy() -> dict[str, Any]:
    try:
        with open(_CONTENT_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
