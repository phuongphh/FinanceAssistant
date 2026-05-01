"""Stateless parameter extractors for the rule-based classifier.

Each module exposes a single ``extract(text: str) -> ...`` function.
Stateless and pure so they can be reused by the LLM classifier post-
processing path or by handlers that want to re-validate user input.
"""
from backend.intent.extractors import amount, category, ticker, time_range

__all__ = ["amount", "category", "ticker", "time_range"]
