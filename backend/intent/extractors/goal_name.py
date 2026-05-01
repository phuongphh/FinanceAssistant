"""Goal-name extractor for ``query_goal_progress``.

Pulls the goal phrase out of constructions like
``"muốn đạt được việc mua xe tôi cần phải làm gì"`` →
``"mua xe"``.

Strategy:
- Match an optional verb prefix ("muốn", "để", "muốn đạt được"),
  then a verb of acquisition ("mua", "có", "đạt", "đạt được"),
  then the noun phrase.
- Stop at known clause boundaries ("tôi", "mình", "cần", "phải",
  "thì", "?") so we don't swallow the entire question.

Returns the trimmed noun phrase or None when nothing plausible is
found. Capitalization preserved so the handler can echo the goal back
to the user verbatim.
"""
from __future__ import annotations

import re

# Pattern: optional kicker → "đạt(/được)" or "có(/được)" or "mua"
# → noun phrase up to a clause boundary.
_GOAL_RE = re.compile(
    r"""
    (?:muốn\s+|để\s+|muốn\s+đạt\s+được\s+|làm\s+sao\s+để\s+)?
    (?:đạt\s+được|đạt|có\s+được|có|mua\s+được|mua|làm\s+được|làm)
    \s+
    (?:việc\s+)?
    (?P<goal>[\w\sÀ-ỹà-ỹ]+?)
    \s*
    (?:tôi|mình|thì|cần|phải|làm\s+gì|làm\s+sao|cần\s+bao\s+nhiêu|nữa|bao\s+lâu|\?|$)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Stop words that shouldn't end up alone as a goal name.
_STOP_PHRASES = {"tôi", "mình", "gì", "nào"}


def extract(text: str) -> str | None:
    """Return the goal phrase or None."""
    if not text:
        return None
    match = _GOAL_RE.search(text)
    if not match:
        return None
    goal = match.group("goal").strip(" ?.,;:")
    if not goal or goal.lower() in _STOP_PHRASES:
        return None
    return goal


__all__ = ["extract"]
