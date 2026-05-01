"""Classifier interface — used by both rule-based and LLM classifiers.

The pipeline depends on this Protocol so it can swap implementations
(or stack them) without import cycles.
"""
from __future__ import annotations

from typing import Protocol

from backend.intent.intents import IntentResult


class IntentClassifier(Protocol):
    """Anything that turns text into an IntentResult (or None)."""

    def classify(self, text: str) -> IntentResult | None:
        ...
