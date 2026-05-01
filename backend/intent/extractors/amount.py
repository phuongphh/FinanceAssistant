"""Extract a VND amount from query text.

Thin shim over ``backend.wealth.amount_parser`` (Phase 3A) so the
extractor surface stays uniform with the others. Returns ``int`` (cents
already eliminated by the parser) or None.

The bare-number cutoff at 1000 protects against grabbing "5" or "10"
out of "5 mã" / "top 10" — only numbers ≥1000 plausibly represent VND.
"""
from __future__ import annotations

from decimal import Decimal

from backend.wealth.amount_parser import parse_amount

# Bare numbers below this threshold are too ambiguous to interpret as
# money — could be quantity, percentage, list-position, etc. Anything
# with an explicit unit ("500k", "1tr") bypasses this check because the
# unit removes the ambiguity.
_BARE_NUMBER_FLOOR = 1000


def extract(text: str) -> int | None:
    """Return the parsed VND amount as ``int`` or None.

    Floors:
    - Empty / unparseable → None
    - Bare digit-only input below 1000 → None (too ambiguous)
    - Negative or zero → None (caller validates separately if needed)
    """
    if not text:
        return None
    parsed: Decimal | None = parse_amount(text)
    if parsed is None or parsed <= 0:
        return None

    # If the input was a bare number (no unit), enforce the floor.
    # Easy heuristic: if the parser returned <1000 it can only be from
    # a bare digit, since every unit multiplier (`k`, `tr`, `tỷ`, etc.)
    # produces ≥1000.
    if parsed < _BARE_NUMBER_FLOOR:
        return None

    return int(parsed)


__all__ = ["extract"]
