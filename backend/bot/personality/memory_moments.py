"""Memory Moments — weekly goal reminder (Phase 2, Issue #44).

Users pick a primary_goal during onboarding (save_more / understand /
reach_goal / less_stress). Every Monday at 08:30, we send them a
reminder that ties the goal they chose back to something concrete from
*last week's* data — so the reminder feels personal, not a motivational
poster.

Design
------
- **Templates per goal** with 2-3 variations each, picked at random.
- **Real data, not hardcoded**. Each goal has a context fetcher that
  queries the DB for the one number/phrase the template needs.
- **Skip rules**:
    - user has no primary_goal → skip (nothing to remind about)
    - user inactive in the past 7 days → skip (no last-week data)
- **Tone**: encouraging, never pushy. Framed as "how it's going", not
  "why haven't you done X".
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full
from backend.config.categories import get_category
from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.user import User
from backend.utils.categories import normalize_category

logger = logging.getLogger(__name__)

# Templates inline rather than in a separate YAML because they're
# tightly coupled to the 4 hardcoded goal codes from
# ``onboarding_flow.PRIMARY_GOALS``. If goals become dynamic later,
# extract this — for now single source = onboarding_flow.py.

GOAL_REMINDER_TEMPLATES: dict[str, list[str]] = {
    "save_more": [
        (
            "💰 Chào tuần mới {name}!\n\n"
            "Nhớ bạn đặt mục tiêu 'tiết kiệm nhiều hơn' không? "
            "Tuần trước bạn đã chi {last_week_spent} — {encouragement}"
        ),
        (
            "🌱 Thứ 2 tốt lành {name}!\n\n"
            "Nhắc nhẹ về mục tiêu tiết kiệm của bạn: tuần trước tổng chi là "
            "{last_week_spent}. {encouragement}"
        ),
    ],
    "understand": [
        (
            "📊 Sáng thứ 2 vui {name}!\n\n"
            "Bạn đang muốn 'hiểu mình tiêu vào đâu' — tuần qua top category của bạn là "
            "{top_cat} với {top_amount} ({top_pct}% tổng chi).\n\n"
            "Một insight nhỏ để bắt đầu tuần 💡"
        ),
        (
            "💡 Chào {name}!\n\n"
            "Tuần rồi bạn chi nhiều nhất cho {top_cat} ({top_amount}). "
            "Mỗi tuần mình sẽ surface 1 pattern như vậy để bạn từ từ \"biết mình\" hơn."
        ),
    ],
    "reach_goal": [
        (
            "🎯 Tuần mới mới {name}!\n\n"
            "Mục tiêu '{goal_name}' còn thiếu {remaining} nữa là xong. "
            "Tuần này cùng nhau tiến thêm một chút nhé 💪"
        ),
        (
            "🌟 Chào buổi sáng {name}.\n\n"
            "Nhắc nhỏ: mục tiêu '{goal_name}' đang ở {progress_pct}%. "
            "Còn {remaining} — bạn đang đi đúng hướng."
        ),
    ],
    "less_stress": [
        (
            "🧘 Chào buổi sáng {name}.\n\n"
            "Thư thả nhé — bạn đặt mục tiêu 'bớt stress về tiền' và tuần rồi {positive_signal}. "
            "Thấy chưa? Không cần hoàn hảo, chỉ cần biết là được 🌸"
        ),
        (
            "💚 Chào tuần mới {name}!\n\n"
            "Một tuần thư giãn đã qua. {positive_signal} "
            "Mình ghi nhận điều đó cho bạn."
        ),
    ],
}


# ---------- Activity check -----------------------------------------

async def was_active_last_week(
    db: AsyncSession, user_id: uuid.UUID, *, today: date | None = None
) -> bool:
    """True if the user has at least one non-deleted expense in the last
    7 days. Used to short-circuit reminders for dormant users.
    """
    today = today or date.today()
    since = today - timedelta(days=7)
    stmt = select(func.count()).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= since,
    )
    count = int((await db.execute(stmt)).scalar_one() or 0)
    return count > 0


# ---------- Context fetchers per goal ------------------------------

async def _context_save_more(
    db: AsyncSession, user_id: uuid.UUID, today: date
) -> dict:
    since = today - timedelta(days=7)
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= since,
        Expense.expense_date < today,
    )
    last_week_spent = float((await db.execute(stmt)).scalar_one() or 0)

    # Rolling 4-week baseline (excl. last week) to gauge direction.
    prior_start = today - timedelta(days=35)
    prior_end = today - timedelta(days=7)
    prior_stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= prior_start,
        Expense.expense_date < prior_end,
    )
    prior_total = float((await db.execute(prior_stmt)).scalar_one() or 0)
    prior_weekly_avg = prior_total / 4.0 if prior_total else 0

    # Encouragement message is positive or neutral — never scolding.
    if prior_weekly_avg > 0 and last_week_spent < prior_weekly_avg * 0.9:
        encouragement = "thấp hơn mức trung bình 4 tuần vừa qua — signal tốt đó 🌿"
    elif prior_weekly_avg > 0 and last_week_spent > prior_weekly_avg * 1.1:
        encouragement = (
            "hơi cao hơn trung bình một chút, nhưng mỗi tuần mỗi khác. "
            "Tuần này chill một tí cũng được 💚"
        )
    else:
        encouragement = "khá đều đặn. Cứ giữ nhịp này nhé 🙂"

    return {
        "last_week_spent": format_money_full(last_week_spent),
        "encouragement": encouragement,
    }


async def _context_understand(
    db: AsyncSession, user_id: uuid.UUID, today: date
) -> dict | None:
    since = today - timedelta(days=7)
    stmt = (
        select(Expense.category, func.sum(Expense.amount).label("total"))
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
            Expense.expense_date >= since,
            Expense.expense_date < today,
        )
        .group_by(Expense.category)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return None

    # Collapse legacy codes (food_drink → food, etc.) before picking top.
    totals: dict[str, float] = {}
    for row in rows:
        key = normalize_category(row.category)
        totals[key] = totals.get(key, 0.0) + float(row.total)
    grand_total = sum(totals.values())
    if grand_total <= 0:
        return None
    top_code, top_total = max(totals.items(), key=lambda kv: kv[1])
    cat = get_category(top_code)
    return {
        "top_cat": cat.name_vi,
        "top_amount": format_money_full(top_total),
        "top_pct": f"{int(round((top_total / grand_total) * 100))}",
    }


async def _context_reach_goal(
    db: AsyncSession, user_id: uuid.UUID, today: date
) -> dict | None:
    """Pick the nearest-deadline active goal. No goal → no message
    (returning None signals caller to skip)."""
    stmt = (
        select(Goal)
        .where(
            Goal.user_id == user_id,
            Goal.is_active.is_(True),
            Goal.deleted_at.is_(None),
        )
        .order_by(
            Goal.deadline.asc().nulls_last(),
            Goal.created_at.desc(),
        )
        .limit(1)
    )
    goal = (await db.execute(stmt)).scalar_one_or_none()
    if goal is None:
        return None

    target = float(goal.target_amount)
    current = float(goal.current_amount)
    remaining = max(0.0, target - current)
    pct = 0.0
    if target > 0:
        pct = min(100.0, (current / target) * 100.0)

    return {
        "goal_name": goal.goal_name,
        "remaining": format_money_full(remaining),
        "progress_pct": f"{int(round(pct))}",
    }


async def _context_less_stress(
    db: AsyncSession, user_id: uuid.UUID, today: date
) -> dict:
    """Find a positive signal in the last 7 days. Always returns a dict
    (positive framing is the whole point — never return None)."""
    since = today - timedelta(days=7)
    prior_start = today - timedelta(days=14)
    prior_end = since

    # Compare last-week total to the prior 7 days.
    this_stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= since,
        Expense.expense_date < today,
    )
    prior_stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= prior_start,
        Expense.expense_date < prior_end,
    )
    this_week = float((await db.execute(this_stmt)).scalar_one() or 0)
    prior_week = float((await db.execute(prior_stmt)).scalar_one() or 0)

    # Count categories where this week <= prior week (green signals).
    cat_stmt = (
        select(Expense.category, func.sum(Expense.amount).label("total"))
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
            Expense.expense_date >= since,
            Expense.expense_date < today,
        )
        .group_by(Expense.category)
    )
    cat_rows = (await db.execute(cat_stmt)).all()
    active_categories = len(cat_rows)

    if prior_week > 0 and this_week < prior_week:
        positive = (
            f"tổng chi tuần rồi thấp hơn tuần trước đó — "
            f"giảm được {format_money_full(prior_week - this_week)} 🌿"
        )
    elif active_categories >= 3:
        positive = (
            f"bạn vẫn ghi đều {active_categories} danh mục khác nhau — "
            "có tổ chức là dấu hiệu tốt 🌱"
        )
    else:
        positive = "tuần vừa rồi khá ổn định, không có gì bất ngờ."

    return {"positive_signal": positive}


# ---------- Public API ---------------------------------------------

async def render_goal_reminder(
    db: AsyncSession, user: User, *, today: date | None = None
) -> Optional[str]:
    """Return the rendered reminder string, or None to skip this user.

    Skip conditions:
    - ``user.primary_goal`` missing or unknown
    - user inactive last 7 days
    - (reach_goal only) user has no active goals
    """
    today = today or date.today()
    if not user.primary_goal:
        return None

    templates = GOAL_REMINDER_TEMPLATES.get(user.primary_goal)
    if not templates:
        logger.debug(
            "render_goal_reminder: unknown primary_goal %r for user %s",
            user.primary_goal, user.id,
        )
        return None

    if not await was_active_last_week(db, user.id, today=today):
        return None

    if user.primary_goal == "save_more":
        ctx = await _context_save_more(db, user.id, today)
    elif user.primary_goal == "understand":
        ctx = await _context_understand(db, user.id, today)
        if ctx is None:
            return None  # no top category = no honest reminder
    elif user.primary_goal == "reach_goal":
        ctx = await _context_reach_goal(db, user.id, today)
        if ctx is None:
            return None  # no goal row = skip rather than invent one
    elif user.primary_goal == "less_stress":
        ctx = await _context_less_stress(db, user.id, today)
    else:
        return None

    ctx["name"] = user.get_greeting_name()
    template = random.choice(templates)
    try:
        return template.format(**ctx)
    except KeyError as exc:
        logger.warning(
            "goal reminder missing placeholder %s for goal=%s",
            exc, user.primary_goal,
        )
        return None
