from __future__ import annotations

import logging

from sqlalchemy import select

from backend.database import get_session_factory
from backend.feedback.services.prompt_scheduler import PromptScheduler
from backend.models.user import User

logger = logging.getLogger(__name__)


async def run_daily_feedback_prompt_check() -> int:
    """Daily 9 AM active-prompt scan for time-based feedback triggers."""
    session_factory = get_session_factory()
    sent_count = 0
    async with session_factory() as db:
        users = list((await db.execute(select(User).where(User.deleted_at.is_(None), User.is_active.is_(True)))).scalars().all())
        scheduler = PromptScheduler()
        for user in users:
            sent_count += len(await scheduler.check_and_send_prompts(db, user.id, event="daily"))
        await db.commit()
    logger.info("Daily feedback prompt check sent %s prompt(s)", sent_count)
    return sent_count
