"""Handler for ``ACTION_ADD_GOAL`` — open the add-goal wizard."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers import goal_entry as goal_entry_handlers
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User

logger = logging.getLogger(__name__)


class ActionAddGoalHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        await goal_entry_handlers.start_goals_wizard(db, user.telegram_id, user)
        return ""
