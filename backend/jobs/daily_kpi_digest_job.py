"""Daily KPI digest cron — single morning operator message (A.6).

Aggregates 5 sections and sends ONE Telegram message to the operator:
  - 💰 Cost (from cost_report_service)
  - 📈 Engagement (DAU/WAU, Twin views, onboarding completed)
  - ✅ Quality (intent accuracy, onboarding emoji breakdown)
  - 💤 Churn signals (users inactive 7+ days, founding-member flag)
  - 📬 Feedback queue (top 3 open)

The operator's Telegram chat_id comes from the ``OPERATOR_TELEGRAM_ID``
env var; absence disables the cron quietly (no crash, no spam).

If anything inside the aggregation throws we still attempt to send a
"⚠️ digest partial" message so the operator knows the cron ran but
hit an issue — silence is the worst failure mode here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session_factory
from backend.feedback.models.feedback import FEEDBACK_STATUS_NEW, Feedback
from backend.models.event import Event
from backend.models.onboarding_session import (
    OnboardingSession,
    STEP_COMPLETED,
)
from backend.models.user import User
from backend.wealth.models.asset import Asset
from backend.ports.notifier import get_notifier
from backend.services.cost.cost_report_service import daily_summary
from backend.services.survey.positioning_survey_service import kpi_snapshot, load_copy

logger = logging.getLogger(__name__)

# Telegram per-message hard limit; we stay well below for inline-keyboard
# safety + readability.
TELEGRAM_MESSAGE_MAX_CHARS = 3800


@dataclass
class EngagementSection:
    dau: int = 0
    wau: int = 0
    twin_views_24h: int = 0
    onboarding_completed_24h: int = 0

    def render(self) -> str:
        return (
            "<b>📈 Engagement (24h)</b>\n"
            f"• DAU: {self.dau} | WAU: {self.wau}\n"
            f"• Twin view: {self.twin_views_24h}\n"
            f"• Onboarding done: {self.onboarding_completed_24h}"
        )


@dataclass
class QualitySection:
    onboarding_signals: dict[str, int]
    data_quality_warning_count: int = 0

    def render(self) -> str:
        love = self.onboarding_signals.get("love", 0)
        confused = self.onboarding_signals.get("confused", 0)
        dislike = self.onboarding_signals.get("dislike", 0)
        return (
            "<b>✅ Quality (24h)</b>\n"
            f"• Onboarding feedback: 😍{love} / 🤔{confused} / 😕{dislike}\n"
            f"• data_quality_warning_count: {self.data_quality_warning_count}"
        )


@dataclass
class ChurnSection:
    inactive_7d: int
    inactive_founding: int

    def render(self) -> str:
        founding_clause = (
            f" (gồm {self.inactive_founding} founding)"
            if self.inactive_founding
            else ""
        )
        return (
            "<b>💤 Churn signals</b>\n"
            f"• Inactive 7+ ngày: {self.inactive_7d}{founding_clause}"
        )


@dataclass
class PositioningSection:
    counts: dict[str, int]
    total: int
    aligned_percent: float
    misaligned_percent: float
    should_alert: bool
    target_aligned_percent: int
    alert_misaligned_percent: int
    minimum_responses_for_alert: int

    def render(self) -> str:
        copy = load_copy()
        lines = ["<b>🧭 Positioning</b>"]
        if self.total == 0:
            lines.append("• Chưa có response Day 7 survey")
        else:
            for option in copy.options:
                count = self.counts.get(option.key, 0)
                percent = count / self.total * 100 if self.total else 0.0
                lines.append(f"• {option.label}: {percent:.0f}% ({count})")
        lines.append(
            f"• Aligned (option 2/3): {self.aligned_percent:.0f}% "
            f"(target ≥ {self.target_aligned_percent}%)"
        )
        alert_prefix = "🚨 " if self.should_alert else ""
        lines.append(
            f"• {alert_prefix}Misaligned (option 1/4): {self.misaligned_percent:.0f}% "
            f"(alert > {self.alert_misaligned_percent}%, n≥{self.minimum_responses_for_alert})"
        )
        return "\n".join(lines)


@dataclass
class FeedbackSection:
    top_open: list[tuple[str, int, str]]  # (id_short, age_hours, snippet)

    def render(self) -> str:
        if not self.top_open:
            return "<b>📬 Feedback</b>\n• Hộp inbox sạch ✨"
        lines = ["<b>📬 Feedback (top 3 open)</b>"]
        for id_short, age_h, snippet in self.top_open[:3]:
            lines.append(f"• <code>{id_short}</code> ({age_h}h): {snippet[:60]}")
        return "\n".join(lines)


# ---------- Section aggregators --------------------------------------


async def _engagement(db: AsyncSession, *, day: date) -> EngagementSection:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    week_start = end - timedelta(days=7)

    # Twin-view events live in the existing Event table.
    twin_views = (
        await db.execute(
            select(func.count())
            .select_from(Event)
            .where(
                Event.event_type == "TWIN_VIEW",
                Event.created_at >= start,
                Event.created_at < end,
            )
        )
    ).scalar() or 0

    # DAU/WAU from any event.
    dau = (
        await db.execute(
            select(func.count(distinct(Event.user_id))).where(
                Event.created_at >= start, Event.created_at < end
            )
        )
    ).scalar() or 0
    wau = (
        await db.execute(
            select(func.count(distinct(Event.user_id))).where(
                Event.created_at >= week_start, Event.created_at < end
            )
        )
    ).scalar() or 0

    onboarding_done = (
        await db.execute(
            select(func.count())
            .select_from(OnboardingSession)
            .where(
                OnboardingSession.current_step == STEP_COMPLETED,
                OnboardingSession.completed_at >= start,
                OnboardingSession.completed_at < end,
            )
        )
    ).scalar() or 0

    return EngagementSection(
        dau=int(dau),
        wau=int(wau),
        twin_views_24h=int(twin_views),
        onboarding_completed_24h=int(onboarding_done),
    )


async def _quality(db: AsyncSession, *, day: date) -> QualitySection:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    rows = (
        await db.execute(
            select(
                OnboardingSession.onboarding_feedback_signal,
                func.count(),
            )
            .where(
                OnboardingSession.onboarding_feedback_signal.is_not(None),
                OnboardingSession.updated_at >= start,
                OnboardingSession.updated_at < end,
            )
            .group_by(OnboardingSession.onboarding_feedback_signal)
        )
    ).all()
    warning_count = (
        await db.execute(
            select(func.count())
            .select_from(Asset)
            .where(
                Asset.data_quality_warning_at >= start,
                Asset.data_quality_warning_at < end,
            )
        )
    ).scalar() or 0
    return QualitySection(
        onboarding_signals={signal: int(count) for signal, count in rows},
        data_quality_warning_count=int(warning_count),
    )


async def _churn(db: AsyncSession, *, day: date) -> ChurnSection:
    cutoff = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(
        days=7
    )

    # Users with no event in 7 days.
    active_subq = (
        select(distinct(Event.user_id)).where(Event.created_at >= cutoff).subquery()
    )
    inactive_count = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.id.not_in(select(active_subq)),
            )
        )
    ).scalar() or 0
    inactive_founding = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.is_founding_member.is_(True),
                User.id.not_in(select(active_subq)),
            )
        )
    ).scalar() or 0
    return ChurnSection(int(inactive_count), int(inactive_founding))


async def _positioning(db: AsyncSession) -> PositioningSection:
    snapshot = await kpi_snapshot(db)
    return PositioningSection(
        counts=snapshot.counts,
        total=snapshot.total,
        aligned_percent=snapshot.aligned_percent,
        misaligned_percent=snapshot.misaligned_percent,
        should_alert=snapshot.should_alert,
        target_aligned_percent=snapshot.target_aligned_percent,
        alert_misaligned_percent=snapshot.alert_misaligned_percent,
        minimum_responses_for_alert=snapshot.minimum_responses_for_alert,
    )


async def _feedback_queue(db: AsyncSession) -> FeedbackSection:
    rows = (
        await db.execute(
            select(Feedback.id, Feedback.created_at, Feedback.content)
            .where(
                Feedback.status == FEEDBACK_STATUS_NEW,
                Feedback.first_responded_at.is_(None),
            )
            .order_by(Feedback.created_at.asc())
            .limit(3)
        )
    ).all()
    now = datetime.now(timezone.utc)
    top = []
    for fid, created_at, content in rows:
        created = (
            created_at.replace(tzinfo=timezone.utc)
            if created_at.tzinfo is None
            else created_at
        )
        age_h = max(int((now - created).total_seconds() // 3600), 0)
        top.append((str(fid)[:8], age_h, content or ""))
    return FeedbackSection(top_open=top)


# ---------- Compose + send -------------------------------------------


async def compose_digest(db: AsyncSession, *, day: date | None = None) -> str:
    if day is None:
        day = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    cost = await daily_summary(db, day=day)
    eng = await _engagement(db, day=day)
    qual = await _quality(db, day=day)
    churn = await _churn(db, day=day)
    positioning = await _positioning(db)
    fb = await _feedback_queue(db)

    parts = [
        f"<b>📊 Bé Tiền KPI digest {day.isoformat()}</b>",
        cost.to_telegram_section(),
        eng.render(),
        qual.render(),
        churn.render(),
        positioning.render(),
        fb.render(),
    ]
    return "\n\n".join(parts)[:TELEGRAM_MESSAGE_MAX_CHARS]


async def run_daily_kpi_digest_job() -> bool:
    """Cron entry point. Returns True if a message was sent."""
    operator_chat_raw = os.environ.get("OPERATOR_TELEGRAM_ID", "").strip()
    if not operator_chat_raw:
        logger.info("OPERATOR_TELEGRAM_ID not set; KPI digest skipped")
        return False
    try:
        operator_chat_id = int(operator_chat_raw)
    except ValueError:
        logger.error("OPERATOR_TELEGRAM_ID is not numeric")
        return False

    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            text = await compose_digest(db)
        except Exception:
            logger.exception("KPI digest compose failed")
            text = "⚠️ KPI digest gặp lỗi khi tổng hợp — kiểm tra Sentry."
            try:
                from backend.adapters.observability import sentry_adapter

                sentry_adapter.capture_exception(Exception("KPI digest compose failed"))
            except Exception:
                pass

    notifier = get_notifier()
    try:
        await notifier.send_message(
            chat_id=operator_chat_id, text=text, parse_mode="HTML"
        )
    except Exception:
        logger.exception("KPI digest send failed")
        return False
    return True
