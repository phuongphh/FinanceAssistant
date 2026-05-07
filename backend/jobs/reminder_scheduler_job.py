"""Daily cron — send reminders for upcoming recurring expenses.

Phase 3.8 Epic 3 (Story P3.8-S9). Runs at 09:00 Asia/Ho_Chi_Minh
(early enough to fit in the user's morning routine, late enough that
overnight events have settled).

For each active pattern with ``enable_reminders=True``:
1. Compute next_expected_date via ``recurring_service``.
2. If ``next_expected_date - today > reminder_days_before``, skip
   (not due yet).
3. If ``snooze_until`` is in the future, skip.
4. If a transaction already linked to this pattern exists in the
   current period, skip ("you already paid").
5. If we already sent a reminder today (``last_reminder_sent ==
   today``), skip.
6. Bundle: if the user has ≥3 due-soon patterns the SAME day, send
   ONE combined message (with bundled keyboard) instead of N pings.
7. Send the reminder + stamp ``last_reminder_sent``.

Telegram failures roll back the per-user transaction so the
``last_reminder_sent`` stamp doesn't tick without delivery.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.bot.keyboards.recurring_keyboard import (
    reminder_action_keyboard,
    reminder_bundle_keyboard,
)
from backend.config.categories import get_category
from backend.database import get_session_factory
from backend.models.recurring_pattern import RecurringPattern
from backend.models.user import User
from backend.profile.models.user_profile import UserProfile
from backend.services import recurring_service
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)


# A user with this many distinct patterns due TODAY gets one
# bundled message instead of three pings. 3 = the spec threshold.
BUNDLE_THRESHOLD = 3
REMINDER_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
WINDOW_MINUTES = 15


async def run_reminder_scheduler(*, now: datetime | None = None) -> None:
    """Entry point for the APScheduler cron registration."""
    now = now or datetime.now(REMINDER_TIMEZONE)
    session_factory = get_session_factory()
    async with session_factory() as db:
        # Pull due patterns + group by user. One DB session for the
        # discovery step keeps the read consistent.
        by_user = await _load_due_patterns_by_user(db)

    logger.info(
        "reminder scheduler: %d users with due patterns", len(by_user),
    )

    for user_id, patterns in by_user.items():
        async with session_factory() as user_db:
            try:
                user = await user_db.get(User, user_id)
                if user is None or user.deleted_at is not None:
                    continue
                profile = await user_db.get(UserProfile, user_id)
                if not _should_send_reminders_now(profile, now=now):
                    continue
                await _send_for_user(user_db, user, patterns)
                await user_db.commit()
            except Exception:
                await user_db.rollback()
                logger.exception(
                    "reminder send failed for user %s", user_id,
                )


def _is_within_15_min(now: time, target: time) -> bool:
    now_min = now.hour * 60 + now.minute
    target_min = target.hour * 60 + target.minute
    delta = (now_min - target_min) % (24 * 60)
    return delta < WINDOW_MINUTES


def _should_send_reminders_now(
    profile: UserProfile | None,
    *,
    now: datetime,
) -> bool:
    if profile is None:
        return _is_within_15_min(now.time(), time(9, 0))
    if not profile.reminder_enabled:
        return False
    return _is_within_15_min(now.time(), profile.reminder_time or time(9, 0))


# ---------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------


async def _load_due_patterns_by_user(
    db, *, today: date | None = None,
) -> dict:
    """Return ``{user_id: [pattern, ...]}`` of patterns due-soon
    today.

    "Due-soon" means ``next_expected_date - today <= reminder_days_
    before``. We compute that in Python (rather than SQL) because
    next_expected_date depends on per-pattern ``last_occurrence_date``
    + month-end clamping.
    """
    today = today or date.today()
    stmt = (
        select(RecurringPattern)
        .where(
            RecurringPattern.is_active.is_(True),
            RecurringPattern.enable_reminders.is_(True),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()

    by_user: dict = {}
    for pattern in rows:
        if pattern.snooze_until and pattern.snooze_until > today:
            continue
        if pattern.last_reminder_sent == today:
            continue
        next_date = recurring_service.get_next_expected_date(
            pattern, today=today,
        )
        days_until = (next_date - today).days
        if days_until > pattern.reminder_days_before:
            continue
        if days_until < 0:
            # Past-due — still worth one ping per day until paid.
            pass
        # Skip if already paid this period.
        if await recurring_service.was_paid_this_period(
            db, pattern, today=today,
        ):
            continue

        by_user.setdefault(pattern.user_id, []).append(pattern)
    return by_user


# ---------------------------------------------------------------------
# Per-user delivery
# ---------------------------------------------------------------------


async def _send_for_user(
    db, user: User, patterns: list[RecurringPattern],
    *, today: date | None = None,
) -> None:
    today = today or date.today()
    if not patterns:
        return

    # Bundle the patterns whose next_expected_date is the same day,
    # to avoid 3 separate pings stacked in the chat. Patterns due on
    # different days each get their own message.
    by_due_date: dict = {}
    for p in patterns:
        d = recurring_service.get_next_expected_date(p, today=today)
        by_due_date.setdefault(d, []).append(p)

    for due_date, group in by_due_date.items():
        if len(group) >= BUNDLE_THRESHOLD:
            await _send_bundled(db, user, group, today=today)
        else:
            for pattern in group:
                await _send_single(db, user, pattern, today=today)


async def _send_single(
    db, user: User, pattern: RecurringPattern,
    *, today: date,
) -> None:
    next_date = recurring_service.get_next_expected_date(pattern, today=today)
    text = _format_single_reminder(pattern, next_date, today=today)
    await send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reminder_action_keyboard(pattern.id),
    )
    pattern.last_reminder_sent = today
    pattern.updated_at = datetime.utcnow()


async def _send_bundled(
    db, user: User, patterns: list[RecurringPattern],
    *, today: date,
) -> None:
    text = _format_bundled_reminder(patterns)
    pattern_ids = [p.id for p in patterns]
    await send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reminder_bundle_keyboard(pattern_ids),
    )
    for p in patterns:
        p.last_reminder_sent = today
        p.updated_at = datetime.utcnow()


# ---------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------


def _format_single_reminder(
    pattern: RecurringPattern, next_date: date, *, today: date,
) -> str:
    """Match spec § P3.8-S9 message format."""
    days_until = (next_date - today).days
    if days_until == 0:
        urgency = "Hôm nay"
    elif days_until == 1:
        urgency = "Ngày mai"
    elif days_until < 0:
        urgency = "Quá hạn"
    else:
        urgency = f"{days_until} ngày nữa"

    cat = get_category(pattern.category)
    return (
        f"⏰ Nhắc nhẹ — {urgency} là tới hạn:\n\n"
        f"{cat.emoji} <b>{pattern.name}</b>\n"
        f"📅 Dự kiến: {next_date.strftime('%d/%m')}\n"
        f"💰 Khoảng {int(Decimal(pattern.expected_amount)):,}đ\n\n"
        "Bạn đã trả chưa?"
    )


def _format_bundled_reminder(patterns: list[RecurringPattern]) -> str:
    """Spec format for bundled reminders (≥3 patterns due same day)."""
    lines = [f"📋 Hôm nay có {len(patterns)} khoản đến hạn:", ""]
    total = Decimal(0)
    for p in patterns:
        cat = get_category(p.category)
        amount = Decimal(p.expected_amount)
        total += amount
        lines.append(
            f"{cat.emoji} {p.name} — {int(amount):,}đ"
        )
    lines.append("")
    lines.append(f"<b>Tổng:</b> {int(total):,}đ")
    return "\n".join(lines)
