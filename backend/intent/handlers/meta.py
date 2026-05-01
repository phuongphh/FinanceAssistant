"""Lightweight handlers for greeting / help / unclear / out-of-scope.

These don't hit the DB — they just compose a friendly response. Kept
in a single module because each one is ~10 lines and they share the
"read the user's display_name once" pattern.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User


class GreetingHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        name = user.display_name or "bạn"
        return (
            f"Chào {name}! 👋\n\n"
            "Mình là Bé Tiền — Personal CFO của bạn. Hôm nay mình giúp gì được?\n"
            "• 'tài sản của tôi'\n"
            "• 'chi tiêu tháng này'\n"
            "• 'VNM giá bao nhiêu'\n\n"
            "Hoặc gõ /menu để xem đầy đủ tính năng."
        )


class HelpHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        name = user.display_name or "bạn"
        return (
            f"{name} có thể hỏi mình bằng tiếng Việt tự nhiên 💬\n\n"
            "*Tài sản & wealth:*\n"
            "• 'tài sản của tôi có gì'\n"
            "• 'tổng tài sản bao nhiêu'\n"
            "• 'portfolios chứng khoán'\n\n"
            "*Chi tiêu:*\n"
            "• 'chi tiêu tháng này'\n"
            "• 'chi tiêu cho ăn uống tháng trước'\n\n"
            "*Thị trường:*\n"
            "• 'VNM giá bao nhiêu'\n"
            "• 'bitcoin giá hôm nay'\n\n"
            "*Mục tiêu & thu nhập:*\n"
            "• 'mục tiêu của tôi'\n"
            "• 'thu nhập của tôi'\n\n"
            "Hoặc tap /menu để xem các tính năng chính."
        )


class UnclearHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        name = user.display_name or "bạn"
        return (
            f"Mình chưa hiểu lắm {name} ơi 🤔\n\n"
            "Bạn thử hỏi:\n"
            "• 'Tài sản của tôi có gì?'\n"
            "• 'Chi tiêu tháng này?'\n"
            "• 'VNM giá bao nhiêu?'\n\n"
            "Hoặc gõ /help để xem đầy đủ."
        )


class OutOfScopeHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        name = user.display_name or "bạn"
        return (
            f"Mình chưa biết trả lời câu này {name} ạ 😅\n\n"
            "Mình chuyên về tài chính cá nhân — tài sản, chi tiêu, thu nhập, "
            "đầu tư VN, mục tiêu.\n"
            "Bạn thử hỏi cách khác xem?"
        )
