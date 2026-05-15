"""Handler for ``ACTION_EDIT_ASSET`` — open the asset edit dashboard.

Triggered by free-text like "sửa cổ phiếu FPT", "sửa đất ba tư",
"sửa bất động sản". When ``asset_type`` is extracted, the picker shows
only matching rows; otherwise the full dashboard is rendered. The
wizard rows themselves carry the ✏️ / 🗑️ buttons so the user can
finish the edit with one more tap.

Returns "" so the dispatcher skips the duplicate plain-text send.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.telegram_service import send_message
from backend.bot.handlers import asset_entry as asset_entry_handlers
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.wealth.services import asset_service

logger = logging.getLogger(__name__)


class ActionEditAssetHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        asset_type = (intent.parameters or {}).get("asset_type")
        chat_id = user.telegram_id

        if asset_type:
            assets = await asset_service.get_user_assets(db, user.id)
            matches = [
                a for a in assets if str(a.asset_type) == asset_type and a.is_active
            ]
            if len(matches) == 1:
                await asset_entry_handlers.start_asset_edit_wizard(
                    db, chat_id, user, str(matches[0].id)
                )
                return ""
            if len(matches) > 1:
                ids = [str(a.id) for a in matches]
                await asset_entry_handlers.show_asset_edit_picker(
                    db, chat_id, user, ids
                )
                return ""
            # No matches of that type — fall through to the full dashboard
            # with a hint, so the user still sees what they own.
            await send_message(
                chat_id=chat_id,
                text=(
                    "Mình không tìm thấy tài sản loại này 🌱 — đây là toàn bộ "
                    "danh mục, bạn chọn dòng cần sửa nhé."
                ),
            )

        await asset_entry_handlers.show_asset_dashboard_report(db, chat_id, user)
        return ""
