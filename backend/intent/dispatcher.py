"""Confidence-aware dispatcher.

Routes ``IntentResult`` → concrete handler. Confidence policy:

  ≥ 0.8        → execute immediately
  0.5 - 0.8    → read intents execute (read is safe); write intents
                 fall back to UNCLEAR (Epic 2 will add confirm flow)
  < 0.5        → UNCLEAR or OUT_OF_SCOPE message

Handlers are instantiated lazily on first dispatch — keeps app startup
cheap and avoids importing the SQLAlchemy models from this module's
top level (the meta handlers do, but everything else is wrapped).
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.intent.handlers.base import IntentHandler
from backend.intent.handlers.meta import (
    GreetingHandler,
    HelpHandler,
    OutOfScopeHandler,
    UnclearHandler,
)
from backend.intent.intents import IntentResult, IntentType
from backend.models.user import User

logger = logging.getLogger(__name__)

# Confidence boundaries — see CLAUDE.md § Phase 3.5 design philosophy.
EXECUTE_THRESHOLD = 0.8
CONFIRM_THRESHOLD = 0.5

READ_INTENTS = frozenset({
    IntentType.QUERY_ASSETS,
    IntentType.QUERY_NET_WORTH,
    IntentType.QUERY_PORTFOLIO,
    IntentType.QUERY_EXPENSES,
    IntentType.QUERY_EXPENSES_BY_CATEGORY,
    IntentType.QUERY_INCOME,
    IntentType.QUERY_CASHFLOW,
    IntentType.QUERY_MARKET,
    IntentType.QUERY_GOALS,
    IntentType.QUERY_GOAL_PROGRESS,
})


class IntentDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[IntentType, IntentHandler] = {}
        # Meta handlers are cheap and have no DB deps — eager init keeps
        # them out of the lazy-load critical path.
        self._meta = {
            IntentType.GREETING: GreetingHandler(),
            IntentType.HELP: HelpHandler(),
            IntentType.UNCLEAR: UnclearHandler(),
            IntentType.OUT_OF_SCOPE: OutOfScopeHandler(),
        }

    async def dispatch(
        self,
        result: IntentResult,
        user: User,
        db: AsyncSession,
    ) -> str:
        # Meta intents short-circuit the confidence policy.
        if result.intent in self._meta:
            return await self._meta[result.intent].handle(result, user, db)

        if result.confidence < CONFIRM_THRESHOLD:
            return await self._meta[IntentType.UNCLEAR].handle(
                result, user, db
            )

        # 0.5 – 0.8: read intents are safe, write intents fall back to
        # UNCLEAR until the confirm flow lands in Epic 2.
        if result.confidence < EXECUTE_THRESHOLD:
            if result.intent not in READ_INTENTS:
                return await self._meta[IntentType.UNCLEAR].handle(
                    result, user, db
                )

        handler = self._get_handler(result.intent)
        if handler is None:
            return self._not_implemented(result)

        try:
            return await handler.handle(result, user, db)
        except Exception:
            logger.exception(
                "Handler error for intent=%s", result.intent.value
            )
            return (
                "Mình đang hơi rối, gặp lỗi khi xử lý 😔\n"
                "Bạn thử lại sau vài phút nhé!"
            )

    # -------------------- handler registry --------------------

    def _get_handler(self, intent: IntentType) -> IntentHandler | None:
        cached = self._handlers.get(intent)
        if cached is not None:
            return cached
        handler = self._build_handler(intent)
        if handler is not None:
            self._handlers[intent] = handler
        return handler

    def _build_handler(self, intent: IntentType) -> IntentHandler | None:
        # Lazy imports so the app can boot without instantiating SQLAlchemy
        # session machinery up front. One module per intent keeps the
        # mapping easy to follow.
        if intent == IntentType.QUERY_ASSETS:
            from backend.intent.handlers.query_assets import (
                QueryAssetsHandler,
            )
            return QueryAssetsHandler()
        if intent == IntentType.QUERY_NET_WORTH:
            from backend.intent.handlers.query_net_worth import (
                QueryNetWorthHandler,
            )
            return QueryNetWorthHandler()
        if intent == IntentType.QUERY_PORTFOLIO:
            from backend.intent.handlers.query_portfolio import (
                QueryPortfolioHandler,
            )
            return QueryPortfolioHandler()
        if intent == IntentType.QUERY_EXPENSES:
            from backend.intent.handlers.query_expenses import (
                QueryExpensesHandler,
            )
            return QueryExpensesHandler()
        if intent == IntentType.QUERY_EXPENSES_BY_CATEGORY:
            from backend.intent.handlers.query_expenses import (
                QueryExpensesByCategoryHandler,
            )
            return QueryExpensesByCategoryHandler()
        if intent == IntentType.QUERY_INCOME:
            from backend.intent.handlers.query_income import (
                QueryIncomeHandler,
            )
            return QueryIncomeHandler()
        if intent == IntentType.QUERY_CASHFLOW:
            # Cashflow not yet implemented as a dedicated handler — show
            # the user the closest approximation (expense listing) plus
            # a "coming soon" hint.
            from backend.intent.handlers.query_expenses import (
                QueryExpensesHandler,
            )
            return QueryExpensesHandler()
        if intent == IntentType.QUERY_MARKET:
            from backend.intent.handlers.query_market import (
                QueryMarketHandler,
            )
            return QueryMarketHandler()
        if intent == IntentType.QUERY_GOALS:
            from backend.intent.handlers.query_goals import (
                QueryGoalsHandler,
            )
            return QueryGoalsHandler()
        if intent == IntentType.QUERY_GOAL_PROGRESS:
            from backend.intent.handlers.query_goals import (
                QueryGoalProgressHandler,
            )
            return QueryGoalProgressHandler()
        return None

    def _not_implemented(self, result: IntentResult) -> str:
        # Used for intents recognised by the classifier but without a
        # handler yet (advisory, planning, action_*).  Friendlier than
        # the unclear fallback because we DID understand the user.
        intent_label = {
            IntentType.ADVISORY: "tư vấn đầu tư",
            IntentType.PLANNING: "lập kế hoạch tài chính",
            IntentType.ACTION_RECORD_SAVING: "ghi tiết kiệm",
            IntentType.ACTION_QUICK_TRANSACTION: "ghi giao dịch nhanh",
        }.get(result.intent, result.intent.value)
        return (
            f"Mình hiểu bạn muốn {intent_label}, "
            "nhưng tính năng này chưa sẵn sàng — coming soon nhé! 🚀"
        )


__all__ = ["IntentDispatcher", "READ_INTENTS"]
