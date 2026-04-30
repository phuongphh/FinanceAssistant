"""Vietnamese-friendly money parser.

Accepts the way Vietnamese users actually type amounts:

    "100 triệu", "100tr", "100tr5"      → 100_000_000 / 100_500_000
    "1.5 tỷ", "1,5 tỷ", "1.5ty"         → 1_500_000_000
    "500k", "500 nghìn", "500 ngàn"     → 500_000
    "VCB 100 triệu"                     → ("VCB", 100_000_000)
    "Techcom 50tr"                      → ("Techcom", 50_000_000)
    "MoMo 2tr"                          → ("MoMo", 2_000_000)
    "5 triệu"                           → ("", 5_000_000)
    "45000"                             → 45_000

Returns ``Decimal`` for the amount and the leftover label as a stripped
string. Designed for the asset-entry wizards — failures return ``None``
so the caller can re-prompt warmly.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


# Capture: optional leading text, a number, an optional decimal part,
# an optional VN unit. We allow comma OR dot as decimal separator
# because Vietnamese keyboards commonly produce both.
# First alternative requires AT LEAST ONE thousand-separator group so it
# only fires for "1,000,000"-style numbers — otherwise "45000" would
# greedy-match the leading "450" and drop the rest.
_AMOUNT_RE = re.compile(
    r"""
    (?P<head>.*?)                                 # optional label
    (?P<int>\d{1,3}(?:[.,]\d{3})+|\d+)            # 1,000,000 or 1000000
    (?:[.,](?P<frac>\d+))?                        # optional .5 or ,5
    \s*
    (?P<unit>tỷ|ty|tỉ|triệu|trieu|tr|nghìn|nghin|ngàn|ngan|k|đ|d|vnđ|vnd)?
    \s*
    (?P<tail>.*)                                  # any trailing crumbs
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Detects a leading-minus before a number, e.g. "-100tr" or "VCB -100 triệu".
# Anchored to start-of-string OR whitespace so that ordinary label dashes
# like "VCB-001 100tr" are not flagged.
_NEGATIVE_RE = re.compile(r"(?:^|\s)-\s*\d")


def has_negative_sign(text: str) -> bool:
    """True if ``text`` has a ``-`` immediately before a number.

    Used by wizard handlers to reject negative amounts with a specific
    "must be > 0" message instead of the generic "couldn't parse" reply.
    The parsers themselves drop the sign silently (the regex doesn't
    capture it), so the caller has to detect this before parsing.
    """
    if not text:
        return False
    return bool(_NEGATIVE_RE.search(text))


_UNIT_MULTIPLIERS = {
    "tỷ": Decimal("1_000_000_000"),
    "ty": Decimal("1_000_000_000"),
    "tỉ": Decimal("1_000_000_000"),
    "triệu": Decimal("1_000_000"),
    "trieu": Decimal("1_000_000"),
    "tr": Decimal("1_000_000"),
    "nghìn": Decimal("1_000"),
    "nghin": Decimal("1_000"),
    "ngàn": Decimal("1_000"),
    "ngan": Decimal("1_000"),
    "k": Decimal("1_000"),
    "đ": Decimal("1"),
    "d": Decimal("1"),
    "vnđ": Decimal("1"),
    "vnd": Decimal("1"),
}


def parse_amount(text: str) -> Decimal | None:
    """Parse the first number-with-unit in ``text`` to a VND ``Decimal``.

    Returns ``None`` if no recognisable number is found.
    """
    if not text:
        return None
    s = text.strip()
    if not s:
        return None

    m = _AMOUNT_RE.match(s)
    if not m:
        return None

    int_part = m.group("int")
    if int_part is None:
        return None

    # Strip thousand separators (we accept both . and , as separators
    # but only when followed by exactly 3 digits — handled in regex).
    int_clean = int_part.replace(",", "").replace(".", "")
    try:
        base = Decimal(int_clean)
    except (InvalidOperation, ValueError):
        return None

    frac = m.group("frac")
    if frac:
        # Decimal fraction interpretation: "1.5" tỷ → 1.5 × 10^9.
        # When unit is present, the frac is the decimal part of the unit
        # multiplier. When absent, it's just trailing digits → ignore.
        try:
            base = base + Decimal(f"0.{frac}")
        except (InvalidOperation, ValueError):
            return None

    unit = (m.group("unit") or "").lower()
    multiplier = _UNIT_MULTIPLIERS.get(unit, Decimal("1"))

    amount = base * multiplier
    return amount


# Match an amount candidate that is "free-standing" — i.e. its leading
# digit sits at start-of-string or right after whitespace. The lookbehind
# is what stops "001" inside "VCB-001" from being read as the amount:
# "001" is preceded by '-', not whitespace, so it isn't a candidate.
# A number with an explicit unit ("100 triệu") is preferred over a bare
# number, so an account label like "VCB-001" with a unit-less typo never
# silently gets misread.
_LABELED_AMOUNT_RE = re.compile(
    r"""
    (?:^|(?<=\s))
    (?P<num>\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)
    \s*
    (?P<unit>tỷ|ty|tỉ|triệu|trieu|tr|nghìn|nghin|ngàn|ngan|k|đ|d|vnđ|vnd)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_label_and_amount(text: str) -> tuple[str, Decimal] | None:
    """Split ``"VCB 100 triệu"`` into ``("VCB", 100_000_000)``.

    Returns ``None`` if no amount can be extracted. The label is whatever
    sits before the number, stripped — empty string is fine ("100tr"
    alone gives ``("", 100_000_000)``).

    Numbers embedded in identifiers ("001" inside "VCB-001") are NOT
    candidates: only digits at start-of-string or after whitespace count.
    Among the free-standing candidates, a number with an explicit unit
    wins; otherwise the first bare number is used. This way "VCB-001 100
    triệu" parses correctly even though the string contains "001" first.
    """
    if not text:
        return None
    s = text.strip()

    candidates = list(_LABELED_AMOUNT_RE.finditer(s))
    if not candidates:
        return None

    # Prefer a candidate that has a unit attached — it's unambiguously
    # an amount. Fall back to the first bare-number candidate.
    chosen = next((m for m in candidates if m.group("unit")), candidates[0])

    label = s[: chosen.start()].strip(" \t\n\r-,.;:")
    amount = parse_amount(chosen.group(0))
    if amount is None or amount <= 0:
        return None
    return label, amount
