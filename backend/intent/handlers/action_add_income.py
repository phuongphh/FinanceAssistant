"""Handler for ``ACTION_ADD_INCOME`` — open the add-income wizard."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers import income_entry as income_entry_handlers
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User

logger = logging.getLogger(__name__)


class ActionAddIncomeHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        await income_entry_handlers.start_income_wizard(
            db, user.telegram_id, user
        )
        return ""
