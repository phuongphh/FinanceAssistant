"""Founding-member operator + user commands (Phase 4.1, C.4).

/whoami           — user-facing profile snapshot (founding flag inline)
/founding_status  — operator view of all founding members
/cohort_stats     — operator breakdown by acquisition source
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.onboarding_session import OnboardingSession
from backend.models.user import User
from backend.services.founding import founding_member_service
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)


_FOUNDING_COPY_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "onboarding"
    / "founding_welcome.yaml"
)


def _copy() -> dict[str, Any]:
    with open(_FOUNDING_COPY_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _is_operator(telegram_id: int | None) -> bool:
    raw = os.environ.get("OPERATOR_TELEGRAM_ID", "").strip()
    if not raw or telegram_id is None:
        return False
    try:
        return int(raw) == int(telegram_id)
    except ValueError:
        return False


# ---------- /whoami --------------------------------------------------


async def cmd_whoami(db: AsyncSession, chat_id: int, user: User | None) -> None:
    if user is None:
        await send_message(chat_id, "Chưa thấy bạn — gõ /start để bắt đầu nhé 🌱")
        return

    copy = _copy()
    session = await db.get(OnboardingSession, user.id)
    segment = (session.inferred_wealth_segment if session else None) or "—"

    onboarded_at = "—"
    if user.onboarding_completed_at:
        onboarded_at = user.onboarding_completed_at.strftime("%d/%m/%Y")

    days_active = 0
    if user.created_at:
        created = (
            user.created_at.replace(tzinfo=timezone.utc)
            if user.created_at.tzinfo is None
            else user.created_at
        )
        days_active = max((datetime.now(timezone.utc) - created).days, 0)

    founding_line = ""
    if user.is_founding_member and user.founding_member_sequence:
        date_str = (
            user.founding_member_at.strftime("%d/%m/%Y")
            if user.founding_member_at
            else "—"
        )
        founding_line = copy["founding_line_template"].format(
            sequence=user.founding_member_sequence,
            founding_date=date_str,
        )

    text = copy["whoami_template"].format(
        display_name=user.display_name or "bạn",
        segment=segment,
        onboarded_at=onboarded_at,
        days_active=days_active,
        founding_line=founding_line,
    )
    await send_message(chat_id, text, parse_mode="HTML")


# ---------- /founding_status (operator) -------------------------------


async def cmd_founding_status(
    db: AsyncSession, chat_id: int, telegram_id: int | None
) -> None:
    if not _is_operator(telegram_id):
        await send_message(chat_id, "Lệnh này chỉ dành cho operator.")
        return

    members = await founding_member_service.list_founding_members(db)
    if not members:
        await send_message(chat_id, "Chưa có Founding Member nào.")
        return

    lines = [f"<b>🌱 Founding Members ({len(members)}/50)</b>"]
    now = datetime.now(timezone.utc)
    for u in members:
        name = u.display_name or "—"
        onboard = (
            u.founding_member_at.strftime("%d/%m") if u.founding_member_at else "—"
        )
        days = 0
        if u.created_at:
            created = (
                u.created_at.replace(tzinfo=timezone.utc)
                if u.created_at.tzinfo is None
                else u.created_at
            )
            days = max((now - created).days, 0)
        lines.append(
            f"#{u.founding_member_sequence:02d} | {name} | onboard {onboard} | {days}d active"
        )
    await send_message(chat_id, "\n".join(lines), parse_mode="HTML")


# ---------- /cohort_stats (operator) ---------------------------------


async def cmd_cohort_stats(
    db: AsyncSession, chat_id: int, telegram_id: int | None
) -> None:
    if not _is_operator(telegram_id):
        await send_message(chat_id, "Lệnh này chỉ dành cho operator.")
        return

    rows = (
        await db.execute(
            select(User.acquisition_source, func.count())
            .where(User.acquisition_source.is_not(None))
            .group_by(User.acquisition_source)
            .order_by(func.count().desc())
        )
    ).all()
    if not rows:
        await send_message(chat_id, "Chưa có user nào có acquisition_source.")
        return

    lines = ["<b>📊 Acquisition source breakdown</b>"]
    total = 0
    for source, count in rows:
        lines.append(f"• {source}: {int(count)}")
        total += int(count)
    lines.append(f"\n<b>Tổng:</b> {total}")
    await send_message(chat_id, "\n".join(lines), parse_mode="HTML")
