"""Handler for ``ACTION_ADD_ASSET`` — open the add-asset wizard.

Triggered by free-text like "thêm bất động sản", "thêm cổ phiếu",
"thêm crypto". The standard `/themtaisan` slash command goes through
the worker directly; this handler is the NLU twin for users who type
the action as a sentence rather than a slash command.

Returns "" so the dispatcher skips the duplicate plain-text send —
the wizard already sent its own message via ``send_message``.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers import asset_entry as asset_entry_handlers
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User

logger = logging.getLogger(__name__)


class ActionAddAssetHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        await asset_entry_handlers.start_asset_wizard(db, user.telegram_id, user)
        return ""
