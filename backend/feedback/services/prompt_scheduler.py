from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.feedback.models.feedback import PROMPT_STATUS_SENT, PROMPT_STATUS_SKIPPED, PromptSentLog
from backend.feedback.services.feedback_service import APP_VERSION, ContextSnapshotService
from backend.models.event import Event
from backend.models.goal import Goal
from backend.models.user import User
from backend.services.telegram_service import send_telegram

PROMPTS_PATH = Path(__file__).resolve().parents[3] / "content" / "feedback_prompts.yaml"
MAX_ACTIVE_PROMPTS_PER_30_DAYS = 2


@dataclass(frozen=True)
class FeedbackPrompt:
    id: str
    trigger: str
    message: str
    cta_button: str
    skip_button: str
    cooldown_days: int


def load_prompts(path: Path = PROMPTS_PATH) -> list[FeedbackPrompt]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [FeedbackPrompt(**item) for item in data.get("prompts", [])]


class PromptScheduler:
    """Strict active feedback prompt scheduler.

    It checks milestone conditions, prompt-specific cooldown, then the hard
    max-2-prompts/30-days cap before sending a Telegram message.
    """

    def __init__(self, prompts: list[FeedbackPrompt] | None = None) -> None:
        self.prompts = prompts or load_prompts()

    async def check_and_send_prompts(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        event: str | None = None,
        now: datetime | None = None,
    ) -> list[str]:
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            return []
        current_time = now or datetime.now(timezone.utc)
        metrics = await self._metrics(db, user, now=current_time)
        sent: list[str] = []
        for prompt in self.prompts:
            if event and event != "daily" and prompt.id != event and not self._event_matches_prompt(event, prompt.id):
                continue
            if event == "daily" and prompt.id not in {"post_onboarding_day_7", "post_3_months_active"}:
                continue
            if not self._condition_met(prompt, metrics):
                continue
            if await self._within_prompt_cooldown(db, user.id, prompt, now=current_time):
                continue
            if await self._hit_monthly_rate_limit(db, user.id, now=current_time):
                break
            await self._send_prompt(db, user, prompt, metrics)
            sent.append(prompt.id)
        return sent

    async def send_prompt(
        self,
        db: AsyncSession,
        user: User,
        prompt_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        prompt = next((item for item in self.prompts if item.id == prompt_id), None)
        if prompt is None:
            return False
        current_time = now or datetime.now(timezone.utc)
        if await self._within_prompt_cooldown(db, user.id, prompt, now=current_time):
            return False
        if await self._hit_monthly_rate_limit(db, user.id, now=current_time):
            return False
        metrics = await self._metrics(db, user, now=current_time)
        await self._send_prompt(db, user, prompt, metrics)
        return True

    async def log_skip(self, db: AsyncSession, user_id: uuid.UUID, prompt_id: str) -> None:
        log = await self._latest_prompt_log(db, user_id, prompt_id)
        if log:
            log.status = PROMPT_STATUS_SKIPPED
            log.skipped_at = datetime.now(timezone.utc)
            await db.flush()

    def _event_matches_prompt(self, event: str, prompt_id: str) -> bool:
        mapping = {
            "briefing_read": "post_briefing_30_reads",
            "goal_completed": "post_first_goal_completed",
            "phase_4_first_view": "post_phase_4_launch",
            "daily": "",
        }
        return mapping.get(event) == prompt_id

    async def _metrics(self, db: AsyncSession, user: User, *, now: datetime) -> dict[str, Any]:
        created_at = user.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        account_age_days = (now - created_at).days if created_at else 0

        briefing_count = await self._event_count(db, user.id, analytics.EventType.MORNING_BRIEFING_OPENED)
        phase_4_count = await self._event_count(db, user.id, "phase_4_first_view")
        goals_completed = int((await db.execute(select(func.count()).where(
            Goal.user_id == user.id,
            Goal.status == "completed",
            Goal.deleted_at.is_(None),
        ))).scalar_one() or 0)
        return {
            "account_age_days": account_age_days,
            "briefing_read_count": briefing_count,
            "goals_completed_count": goals_completed,
            "phase_4_first_view": phase_4_count > 0,
            "app_version": APP_VERSION,
        }

    async def _event_count(self, db: AsyncSession, user_id: uuid.UUID, event_type: str) -> int:
        stmt = select(func.count()).where(Event.user_id == user_id, Event.event_type == event_type)
        return int((await db.execute(stmt)).scalar_one() or 0)

    def _condition_met(self, prompt: FeedbackPrompt, metrics: dict[str, Any]) -> bool:
        return {
            "post_onboarding_day_7": metrics["account_age_days"] == 7,
            "post_briefing_30_reads": metrics["briefing_read_count"] == 30,
            "post_first_goal_completed": metrics["goals_completed_count"] == 1,
            "post_phase_4_launch": metrics["phase_4_first_view"] is True,
            "post_3_months_active": metrics["account_age_days"] == 90,
        }.get(prompt.id, False)

    async def _within_prompt_cooldown(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        prompt: FeedbackPrompt,
        *,
        now: datetime,
    ) -> bool:
        since = now - timedelta(days=prompt.cooldown_days)
        stmt = select(func.count()).where(
            PromptSentLog.user_id == user_id,
            PromptSentLog.prompt_id == prompt.id,
            PromptSentLog.sent_at >= since,
        )
        return int((await db.execute(stmt)).scalar_one() or 0) > 0

    async def _hit_monthly_rate_limit(self, db: AsyncSession, user_id: uuid.UUID, *, now: datetime) -> bool:
        since = now - timedelta(days=30)
        stmt = select(func.count()).where(
            PromptSentLog.user_id == user_id,
            PromptSentLog.sent_at >= since,
        )
        return int((await db.execute(stmt)).scalar_one() or 0) >= MAX_ACTIVE_PROMPTS_PER_30_DAYS

    async def _latest_prompt_log(self, db: AsyncSession, user_id: uuid.UUID, prompt_id: str) -> PromptSentLog | None:
        stmt = (
            select(PromptSentLog)
            .where(PromptSentLog.user_id == user_id, PromptSentLog.prompt_id == prompt_id)
            .order_by(PromptSentLog.sent_at.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _send_prompt(
        self,
        db: AsyncSession,
        user: User,
        prompt: FeedbackPrompt,
        metrics: dict[str, Any],
    ) -> None:
        snapshot = await ContextSnapshotService().capture(db, user)
        snapshot.update(metrics)
        log = PromptSentLog(
            user_id=user.id,
            prompt_id=prompt.id,
            trigger=prompt.id,
            status=PROMPT_STATUS_SENT,
            context=snapshot,
        )
        db.add(log)
        await db.flush()
        await send_telegram(
            "sendMessage",
            {
                "chat_id": user.telegram_id,
                "text": prompt.message,
                "reply_markup": {
                    "inline_keyboard": [[
                        {"text": prompt.cta_button, "callback_data": f"feedback:cta:{prompt.id}"},
                        {"text": prompt.skip_button, "callback_data": f"feedback:skip:{prompt.id}"},
                    ]]
                },
            },
        )


async def check_briefing_read_prompt(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    return await PromptScheduler().check_and_send_prompts(db, user_id, event="briefing_read")


async def check_goal_completed_prompt(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    return await PromptScheduler().check_and_send_prompts(db, user_id, event="goal_completed")


async def check_daily_feedback_prompts(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    return await PromptScheduler().check_and_send_prompts(db, user_id, event="daily")
