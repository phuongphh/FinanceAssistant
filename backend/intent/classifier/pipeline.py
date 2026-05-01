"""Intent classification pipeline.

Layer 1 — RuleBasedClassifier — runs first. Returns immediately on a
high-confidence match. Layer 2 (LLM fallback, Epic 2) is a placeholder
hook so the pipeline stays open for extension without changing call
sites.

If both layers fail, the pipeline returns ``IntentResult(UNCLEAR, 0.0)``
so callers never have to handle ``None`` — making routing logic shorter
and the bot's "I didn't get that" behaviour explicit.
"""
from __future__ import annotations

import logging

from backend.intent.classifier.base import IntentClassifier
from backend.intent.classifier.rule_based import RuleBasedClassifier
from backend.intent.intents import (
    CLASSIFIER_NONE,
    IntentResult,
    IntentType,
)

logger = logging.getLogger(__name__)

# Confidence above which the rule classifier is trusted to short-circuit
# the LLM step. Lower than 0.85 means we *might* prefer to escalate.
HIGH_CONFIDENCE_THRESHOLD = 0.85


class IntentPipeline:
    def __init__(
        self,
        rule_classifier: IntentClassifier | None = None,
        llm_classifier: IntentClassifier | None = None,
    ) -> None:
        self.rule_classifier = rule_classifier or RuleBasedClassifier()
        # Epic 2 wires this in; for now an explicit None makes the
        # intention obvious to readers.
        self.llm_classifier = llm_classifier

    async def classify(self, text: str) -> IntentResult:
        rule_result = self.rule_classifier.classify(text)
        if rule_result and rule_result.confidence >= HIGH_CONFIDENCE_THRESHOLD:
            return rule_result

        if self.llm_classifier is not None:
            try:
                llm_result = await self._llm_classify(text)
            except Exception:
                logger.exception("LLM classifier raised; falling back")
                llm_result = None
            if llm_result is not None:
                return llm_result

        if rule_result is not None:
            return rule_result

        return IntentResult(
            intent=IntentType.UNCLEAR,
            confidence=0.0,
            raw_text=text,
            classifier_used=CLASSIFIER_NONE,
        )

    async def _llm_classify(self, text: str) -> IntentResult | None:
        # The LLM classifier may be sync or async; the Protocol doesn't
        # constrain that. Be conservative — await if we got a coroutine.
        result = self.llm_classifier.classify(text)  # type: ignore[union-attr]
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[assignment]
        return result


__all__ = ["IntentPipeline", "HIGH_CONFIDENCE_THRESHOLD"]
