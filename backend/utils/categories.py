"""Shared category-code normalization.

Before Phase 1 we used legacy codes (``food_drink``, ``savings``,
``utilities``). The shared source of truth in
``backend/config/categories.py`` uses the shorter post-Phase-1 codes
(``food``, ``saving``, ``utility``). Any read path that groups or
displays by category must normalize first — otherwise two logical
groups for the same concept get double-counted.

``dashboard_service`` has its own private copy of this table; when it
stabilises we should collapse that one into this module too.
"""
from __future__ import annotations


_CATEGORY_CODE_ALIASES = {
    "food_drink": "food",
    "utilities": "utility",
    "savings": "saving",
    "needs_review": "other",
}


def normalize_category(code: str | None) -> str:
    """Map a (possibly legacy) category code to the canonical code.

    Falls back to ``"other"`` if ``code`` is empty/None.
    """
    if not code:
        return "other"
    return _CATEGORY_CODE_ALIASES.get(code, code)
