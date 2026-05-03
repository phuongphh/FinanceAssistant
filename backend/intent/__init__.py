"""Intent understanding layer (Phase 3.5).

Public surface re-exports the intent enum + result dataclass so callers
can ``from backend.intent import IntentType, IntentResult`` without
reaching into ``intents.py``.
"""
from backend.intent.intents import IntentResult, IntentType

__all__ = ["IntentResult", "IntentType"]
