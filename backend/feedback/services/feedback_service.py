from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.feedback.models.feedback import Feedback
from backend.models.event import Event
from backend.models.user import User

APP_VERSION = "phase-3.8.5"
MAX_FEEDBACK_PER_DAY = 5
MIN_FEEDBACK_CHARS = 5
MAX_FEEDBACK_CHARS = 5000


class FeedbackValidationError(ValueError):
    """Raised when feedback cannot be accepted from the user."""


class FeedbackRateLimitError(FeedbackValidationError):
    """Raised when user has sent too many feedbacks today."""


async def count_feedbacks_since(
    db: AsyncSession,
    user_id: uuid.UUID,
    since: datetime,
) -> int:
    stmt = select(func.count()).where(
        Feedback.user_id == user_id,
        Feedback.created_at >= since,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def validate_feedback_text(
    db: AsyncSession,
    user_id: uuid.UUID,
    content: str,
    *,
    now: datetime | None = None,
) -> str:
    normalized = (content or "").strip()
    if len(normalized) < MIN_FEEDBACK_CHARS:
        raise FeedbackValidationError("Feedback hơi ngắn quá nè. Bạn viết thêm vài chữ giúp Bé Tiền nhé 💚")
    if len(normalized) > MAX_FEEDBACK_CHARS:
        raise FeedbackValidationError("Feedback dài quá rồi nè (tối đa 5.000 ký tự). Bạn rút gọn giúp Bé Tiền nhé 💚")

    current_time = now or datetime.now(timezone.utc)
    day_start = current_time - timedelta(days=1)
    sent_today = await count_feedbacks_since(db, user_id, day_start)
    if sent_today >= MAX_FEEDBACK_PER_DAY:
        raise FeedbackRateLimitError("Bạn đã gửi 5 feedback trong 24 giờ qua rồi. Mai gửi tiếp giúp Bé Tiền nhé 💚")
    return normalized


class ContextSnapshotService:
    """Capture non-PII context at feedback submission time."""

    async def capture(self, db: AsyncSession, user: User) -> dict[str, Any]:
        account_age_days = None
        if user.created_at:
            created_at = user.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            account_age_days = max(
                0,
                (datetime.now(timezone.utc) - created_at).days,
            )

        return {
            "wealth_level": user.wealth_level or "unknown",
            "account_age_days": account_age_days,
            "recent_actions": await self._recent_actions(db, user.id),
            "active_features": self._active_features(user),
            "app_version": APP_VERSION,
        }

    async def _recent_actions(self, db: AsyncSession, user_id: uuid.UUID) -> list[dict[str, Any]]:
        stmt = (
            select(Event.event_type, Event.timestamp)
            .where(Event.user_id == user_id)
            .order_by(Event.timestamp.desc())
            .limit(5)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "event_type": row.event_type,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in rows
        ]

    def _active_features(self, user: User) -> list[str]:
        features = ["feedback", "menu", "dashboard"]
        if user.briefing_enabled:
            features.append("morning_briefing")
        if user.wizard_state:
            flow = user.wizard_state.get("flow")
            if flow:
                features.append(f"wizard:{flow}")
        return features


async def create_feedback(
    db: AsyncSession,
    user: User,
    content: str,
    *,
    trigger: str = "passive_command",
    context: dict[str, Any] | None = None,
) -> Feedback:
    normalized = await validate_feedback_text(db, user.id, content)
    snapshot = context or await ContextSnapshotService().capture(db, user)
    feedback = Feedback(
        user_id=user.id,
        content=normalized,
        trigger=trigger,
        context=snapshot,
    )
    db.add(feedback)
    await db.flush()
    analytics.track(
        "feedback_submitted",
        user_id=user.id,
        properties={"trigger": trigger, "wealth_level": user.wealth_level or "unknown"},
    )
    return feedback


async def list_unclassified_feedbacks(
    db: AsyncSession,
    *,
    limit: int = 50,
    max_attempts: int = 3,
) -> list[Feedback]:
    stmt = (
        select(Feedback)
        .where(
            Feedback.category.is_(None),
            Feedback.classification_attempts < max_attempts,
        )
        .order_by(Feedback.created_at.asc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())
