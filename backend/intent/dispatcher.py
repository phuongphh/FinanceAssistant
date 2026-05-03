"""Confidence-aware dispatcher with confirm + clarify flows (Epic 2).

Routes ``IntentResult`` → response string. Confidence policy:

  ≥ 0.8        → execute (read or write)
  0.5 – 0.8    → READ : execute (data isn't damaged by reading)
                 WRITE: build confirmation + persist pending action
  < 0.5        → clarify with YAML-templated prompt + persist
                 awaiting-clarification state

Dispatcher returns a ``DispatchOutcome`` (text + optional pending state
description) so the caller (free_form_text) can attach inline keyboards
and clear/restore state appropriately.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.intent import clarifier, pending_action
from backend.intent.handlers.base import IntentHandler
from backend.intent.handlers.meta import (
    GreetingHandler,
    HelpHandler,
    UnclearHandler,
)
from backend.intent.handlers.out_of_scope import OutOfScopeHandler
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

WRITE_INTENTS = frozenset({
    IntentType.ACTION_RECORD_SAVING,
    IntentType.ACTION_QUICK_TRANSACTION,
})

# Intents whose handler output should NOT be wrapped with the
# personality layer. Advisory speaks for itself (LLM-shaped tone +
# legal disclaimer). Meta intents (greeting/help) and action handlers
# also format their own copy.
_SKIP_PERSONALITY_INTENTS = frozenset({
    IntentType.ADVISORY,
    IntentType.PLANNING,
    IntentType.GREETING,
    IntentType.HELP,
    IntentType.ACTION_RECORD_SAVING,
    IntentType.ACTION_QUICK_TRANSACTION,
})


# Outcome kinds — string constants so analytics + tests stay decoupled
# from the dispatcher object.
OUTCOME_EXECUTED = "executed"
OUTCOME_CONFIRM_SENT = "confirm_sent"
OUTCOME_CLARIFY_SENT = "clarify_sent"
OUTCOME_UNCLEAR = "unclear"
OUTCOME_OUT_OF_SCOPE = "out_of_scope"
OUTCOME_NOT_IMPLEMENTED = "not_implemented"
OUTCOME_ERROR = "error"


@dataclass(frozen=True)
class DispatchOutcome:
    """Result of a dispatch — what to send + bookkeeping for callers.

    ``kind`` lets the caller emit the right analytics event without
    re-inspecting the response string. ``inline_keyboard_hint`` carries
    the parsed [Label] options from clarification templates so the
    caller can render Telegram buttons.
    """

    text: str
    kind: str
    intent: IntentType
    confidence: float = 0.0
    inline_keyboard_hint: list[str] | None = None


class IntentDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[IntentType, IntentHandler] = {}
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
    ) -> DispatchOutcome:
        # Meta intents short-circuit the confidence policy entirely.
        if result.intent == IntentType.OUT_OF_SCOPE:
            text = await self._meta[IntentType.OUT_OF_SCOPE].handle(
                result, user, db
            )
            return DispatchOutcome(
                text=text,
                kind=OUTCOME_OUT_OF_SCOPE,
                intent=result.intent,
                confidence=result.confidence,
            )
        if result.intent in (IntentType.GREETING, IntentType.HELP):
            text = await self._meta[result.intent].handle(result, user, db)
            return DispatchOutcome(
                text=text,
                kind=OUTCOME_EXECUTED,
                intent=result.intent,
                confidence=result.confidence,
            )

        # Low confidence — clarify.
        if (
            result.confidence < CONFIRM_THRESHOLD
            or result.intent == IntentType.UNCLEAR
        ):
            return await self._build_clarification(result, user, db)

        # Medium confidence — read intents execute, write intents confirm.
        # Exception: ACTION_QUICK_TRANSACTION executes directly even at
        # medium confidence. The rich expense card already gives the user
        # an undo/edit path, and the LLM classifier doesn't reliably
        # extract ``merchant`` (only ``amount``), so a confirmation
        # prompt would be missing context. Trust the handler's own LLM
        # re-parse to validate intent before persisting.
        if result.confidence < EXECUTE_THRESHOLD:
            if (
                result.intent in WRITE_INTENTS
                and result.intent != IntentType.ACTION_QUICK_TRANSACTION
            ):
                return await self._build_confirmation(result, user, db)
            # Read intents (and ACTION_QUICK_TRANSACTION) fall through.

        # Execute.
        return await self._execute(result, user, db)

    # ------------------------ confirmation ------------------------

    async def _build_confirmation(
        self,
        result: IntentResult,
        user: User,
        db: AsyncSession,
    ) -> DispatchOutcome:
        # Validate the action has the params it needs — if not, it's
        # actually a clarify case (e.g. "tiết kiệm" without an amount).
        if result.intent == IntentType.ACTION_RECORD_SAVING:
            amount = result.parameters.get("amount")
            if not amount:
                return await self._build_clarification(result, user, db)

        text = clarifier.build_action_confirmation(result, user)
        await pending_action.set_pending_action(
            db,
            user,
            intent=result.intent.value,
            parameters=dict(result.parameters or {}),
        )
        return DispatchOutcome(
            text=text,
            kind=OUTCOME_CONFIRM_SENT,
            intent=result.intent,
            confidence=result.confidence,
            inline_keyboard_hint=["✅ Đúng", "❌ Không phải"],
        )

    # ------------------------ clarification ------------------------

    async def _build_clarification(
        self,
        result: IntentResult,
        user: User,
        db: AsyncSession,
    ) -> DispatchOutcome:
        # Truly UNCLEAR (no signal at all) — friendly default; do NOT
        # persist clarification state because there's no original intent
        # to come back to.
        if result.intent == IntentType.UNCLEAR or result.confidence == 0.0:
            text = await self._meta[IntentType.UNCLEAR].handle(
                result, user, db
            )
            return DispatchOutcome(
                text=text,
                kind=OUTCOME_UNCLEAR,
                intent=IntentType.UNCLEAR,
                confidence=result.confidence,
            )

        text = clarifier.build_clarification(result.intent, user)
        keyboard_hint = _extract_button_labels(text)

        await pending_action.set_awaiting_clarification(
            db,
            user,
            intent=result.intent.value,
            raw_text=result.raw_text or "",
            parameters=dict(result.parameters or {}),
        )
        return DispatchOutcome(
            text=text,
            kind=OUTCOME_CLARIFY_SENT,
            intent=result.intent,
            confidence=result.confidence,
            inline_keyboard_hint=keyboard_hint,
        )

    # ------------------------ execute ------------------------

    async def _execute(
        self,
        result: IntentResult,
        user: User,
        db: AsyncSession,
    ) -> DispatchOutcome:
        handler = self._get_handler(result.intent)
        if handler is None:
            return DispatchOutcome(
                text=self._not_implemented(result),
                kind=OUTCOME_NOT_IMPLEMENTED,
                intent=result.intent,
                confidence=result.confidence,
            )
        try:
            text = await handler.handle(result, user, db)
        except Exception:
            logger.exception(
                "Handler error for intent=%s", result.intent.value
            )
            return DispatchOutcome(
                text=(
                    "Mình đang hơi rối, gặp lỗi khi xử lý 😔\n"
                    "Bạn thử lại sau vài phút nhé!"
                ),
                kind=OUTCOME_ERROR,
                intent=result.intent,
                confidence=result.confidence,
            )

        # Phase 3.5 Epic 3 — wrap with personality + follow-up buttons.
        # Skip for advisory (already has its own disclaimer footer + LLM
        # tone) and meta intents (greeting/help format their own copy).
        from backend.bot.personality.query_voice import add_personality
        from backend.intent import follow_up
        from backend.wealth.ladder import detect_level
        from backend.wealth.services import net_worth_calculator

        wrapped = text
        keyboard_hint: list[str] | None = None
        if result.intent not in _SKIP_PERSONALITY_INTENTS:
            wrapped = add_personality(text, user, result.intent)

            # Detect wealth level once for the keyboard. Skip the read
            # roundtrip for handlers that already pulled it (we don't have
            # access to their Style object from here — one DB hit is
            # cheap and the dispatcher path is already async).
            level = None
            try:
                maybe = net_worth_calculator.calculate(db, user.id)
                # Guard against tests passing a sync Mock that returns
                # something not awaitable — produces a clean None level
                # instead of a "never-awaited coroutine" warning.
                import inspect as _inspect
                if _inspect.isawaitable(maybe):
                    breakdown = await maybe
                    level = detect_level(breakdown.total)
            except Exception:
                level = None

            suggestions = follow_up.get_follow_ups(
                result.intent,
                wealth_level=level,
                avoid_intent=result.intent,
            )
            if suggestions:
                keyboard_hint = [fu.label for fu in suggestions]

        return DispatchOutcome(
            text=wrapped,
            kind=OUTCOME_EXECUTED,
            intent=result.intent,
            confidence=result.confidence,
            inline_keyboard_hint=keyboard_hint,
        )

    # ------------------------ handler registry ------------------------

    def _get_handler(self, intent: IntentType) -> IntentHandler | None:
        cached = self._handlers.get(intent)
        if cached is not None:
            return cached
        handler = self._build_handler(intent)
        if handler is not None:
            self._handlers[intent] = handler
        return handler

    def _build_handler(self, intent: IntentType) -> IntentHandler | None:
        if intent == IntentType.ACTION_QUICK_TRANSACTION:
            from backend.intent.handlers.action_quick_transaction import (
                ActionQuickTransactionHandler,
            )
            return ActionQuickTransactionHandler()
        if intent == IntentType.QUERY_ASSETS:
            from backend.intent.handlers.query_assets import QueryAssetsHandler
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
            from backend.intent.handlers.query_cashflow import (
                QueryCashflowHandler,
            )
            return QueryCashflowHandler()
        if intent == IntentType.QUERY_MARKET:
            from backend.intent.handlers.query_market import QueryMarketHandler
            return QueryMarketHandler()
        if intent == IntentType.QUERY_GOALS:
            from backend.intent.handlers.query_goals import QueryGoalsHandler
            return QueryGoalsHandler()
        if intent == IntentType.QUERY_GOAL_PROGRESS:
            from backend.intent.handlers.query_goals import (
                QueryGoalProgressHandler,
            )
            return QueryGoalProgressHandler()
        if intent == IntentType.ADVISORY:
            from backend.intent.handlers.advisory import AdvisoryHandler
            return AdvisoryHandler()
        return None

    def _not_implemented(self, result: IntentResult) -> str:
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


# ------------------------ small helpers ------------------------


def _extract_button_labels(text: str) -> list[str]:
    """Pull ``[Label]`` segments out of a YAML-rendered prompt so the
    caller can build an inline keyboard. Empty list when no buttons.
    """
    import re

    labels: list[str] = []
    for match in re.finditer(r"\[([^\[\]\n]+)\]", text):
        label = match.group(1).strip()
        if label and label not in labels:
            labels.append(label)
    return labels


__all__ = [
    "CONFIRM_THRESHOLD",
    "DispatchOutcome",
    "EXECUTE_THRESHOLD",
    "IntentDispatcher",
    "OUTCOME_CLARIFY_SENT",
    "OUTCOME_CONFIRM_SENT",
    "OUTCOME_ERROR",
    "OUTCOME_EXECUTED",
    "OUTCOME_NOT_IMPLEMENTED",
    "OUTCOME_OUT_OF_SCOPE",
    "OUTCOME_UNCLEAR",
    "READ_INTENTS",
    "WRITE_INTENTS",
]
