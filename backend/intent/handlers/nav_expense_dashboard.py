"""Handler for ``NAV_EXPENSE_DASHBOARD`` — open the expense miniapp.

Triggered by free-text like "chi tiêu dashboard" or "dashboard chi tiêu".
Mirrors the ``_action_expenses_report`` menu path: send a single message
with a WebApp button so the user can tap straight into the dashboard.

Returns "" so the dispatcher skips the duplicate plain-text send.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.telegram_service import send_message
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.miniapp.urls import expense_dashboard_url
from backend.models.user import User

logger = logging.getLogger(__name__)


class NavExpenseDashboardHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        chat_id = user.telegram_id
        url = expense_dashboard_url(source="nlu_expense_dashboard")
        if url is None:
            await send_message(
                chat_id=chat_id,
                text=(
                    "📊 Dashboard chưa sẵn sàng — admin cần cấu hình "
                    "`MINIAPP_BASE_URL` trước nhé."
                ),
                parse_mode="Markdown",
            )
            return ""

        await send_message(
            chat_id=chat_id,
            text="📊 Mở dashboard chi tiêu:",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "Mở Dashboard", "web_app": {"url": url}}],
                ],
            },
        )
        return ""
