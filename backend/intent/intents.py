"""Intent taxonomy + classification result type for Phase 3.5.

The enum is the stable contract every classifier, dispatcher, and
handler agrees on. ``str``-valued so ``IntentResult`` round-trips
through JSON (analytics) and YAML (test fixtures, pattern definitions)
without custom encoders.

Adding a new intent: append a member here, then add (a) a pattern in
``content/intent_patterns.yaml`` or coverage in the LLM classifier
prompt, and (b) a handler in ``backend/intent/handlers/`` plus its
mapping in the dispatcher. Removing intents needs the reverse — and a
data migration if any historical analytics reference the old name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    """All intents Bé Tiền recognises in Phase 3.5."""

    # ----- Read intents -----
    QUERY_ASSETS = "query_assets"
    QUERY_NET_WORTH = "query_net_worth"
    QUERY_PORTFOLIO = "query_portfolio"
    QUERY_EXPENSES = "query_expenses"
    QUERY_EXPENSES_BY_CATEGORY = "query_expenses_by_category"
    QUERY_INCOME = "query_income"
    QUERY_CASHFLOW = "query_cashflow"
    QUERY_MARKET = "query_market"
    QUERY_GOALS = "query_goals"
    QUERY_GOAL_PROGRESS = "query_goal_progress"

    # ----- Action intents (write) -----
    ACTION_RECORD_SAVING = "action_record_saving"
    ACTION_QUICK_TRANSACTION = "action_quick_transaction"

    # ----- Advanced (LLM-routed) -----
    ADVISORY = "advisory"
    PLANNING = "planning"

    # ----- Meta -----
    GREETING = "greeting"
    HELP = "help"
    UNCLEAR = "unclear"
    OUT_OF_SCOPE = "out_of_scope"


# Classifier provenance — kept as plain strings so YAML fixtures and
# analytics events can compare without importing this module.
CLASSIFIER_RULE = "rule"
CLASSIFIER_LLM = "llm"
CLASSIFIER_NONE = "none"


@dataclass
class IntentResult:
    """Output of intent classification.

    ``parameters`` uses ``default_factory=dict`` so each instance owns
    its own dict — sharing one across results would silently mutate
    every previous classification.
    """

    intent: IntentType
    confidence: float
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    classifier_used: str = CLASSIFIER_NONE
    needs_clarification: bool = False
    clarification_question: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly snapshot — used by analytics tracking."""
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "parameters": dict(self.parameters),
            "classifier_used": self.classifier_used,
            "needs_clarification": self.needs_clarification,
        }
