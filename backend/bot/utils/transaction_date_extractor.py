"""Extract a transaction date from free-text user input.

Three detection modes, tried in order so the most disambiguating shape
wins:

  * **Mode 0 — keyword-anchored.** ``ngày``, ``vào ngày``, ``hôm`` +
    ``dd/mm[/yyyy]``. Authoritative whenever present.
  * **Mode 1 — year-bearing anywhere.** A bare ``dd/mm/yyyy`` (or
    ``dd/mm/yy``) sitting anywhere in the message. The explicit year
    disambiguates from ratios/portions ("ăn 12/3 phần" stays untouched
    because it has no year). Lookarounds keep the match out of digit
    runs like phone numbers.
  * **Mode 2 — leading bare dd/mm.** A ``dd/mm`` at the very start of
    the message, followed by more content. To stay safe against ratios
    like ``"1/2 ổ bánh mì 50k"`` we require **day > 12 OR month > 12**.
    Year defaults to ``today.year`` (see :func:`parse_vietnamese_date_token`).

The function returns the date together with the character span covering
what should be stripped from the merchant/note. Mode 0 also covers the
keyword; Modes 1 and 2 cover only the date token. Callers feed the
result through :func:`strip_span` to clean the surrounding text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from backend.bot.utils.date_parser import parse_vietnamese_date_token

# Inner day/month[/year] token. Mirrors ``_VN_DATE_TOKEN_RE`` in
# date_parser.py but stays unanchored so we can embed it in a larger
# phrase regex.
_DATE_TOKEN = r"\d{1,2}[/\-.]\d{1,2}(?:[/\-.](?:\d{2}|\d{4}))?"

# Mode 0 — keyword-anchored. ``ngày`` is canonical; ``vào ngày`` and
# ``hôm`` cover natural phrasings. The keyword shields us from ratios
# (``"ăn 12/3 phần"`` has no keyword and stays put).
_DATE_PHRASE_RE = re.compile(
    rf"(?P<prefix>\b(?:vào\s+ngày|ngày|hôm))\s+(?P<token>{_DATE_TOKEN})\b",
    re.IGNORECASE,
)

# Mode 1 — year-bearing date anywhere. The (?<!\d) / (?!\d) lookarounds
# keep the regex from biting into the middle of a digit run such as
# ``"0902/05/2026"`` (phone number). The 4-digit (or 2-digit) year is
# what tells a date apart from a ratio.
_YEAR_BEARING_DATE_RE = re.compile(
    r"(?<!\d)"
    r"(?P<token>\d{1,2}[/\-.]\d{1,2}[/\-.](?:\d{4}|\d{2}))"
    r"(?!\d)"
)

# Mode 2 — leading bare ``dd/mm`` (no year) followed by at least one
# more token. The day/month numbers are captured separately so we can
# enforce the day>12 OR month>12 disambiguation guard before parsing.
_LEADING_BARE_DATE_RE = re.compile(
    r"^\s*(?P<token>(?P<d>\d{1,2})[/\-.](?P<m>\d{1,2}))(?=\s+\S)"
)


@dataclass(frozen=True)
class ExtractedDate:
    """Result of date extraction.

    ``span`` is the half-open ``(start, end)`` slice in the input text
    that should be stripped from the merchant/note. For Mode 0 it covers
    the keyword and the token; for Modes 1 and 2 it covers only the
    token itself.
    """

    value: date
    span: tuple[int, int]


def extract_transaction_date(
    text: str, *, today: date | None = None
) -> ExtractedDate | None:
    """Find a transaction date in ``text``.

    Returns ``None`` when no recognisable date is present, or when the
    candidate token is malformed (e.g. ``31/02/2026`` → invalid). The
    caller then keeps ``date.today()``. Mode precedence — keyword,
    year-bearing, leading bare — is documented at the module level.
    """
    if not text:
        return None

    # Mode 0 — keyword-anchored phrase (most authoritative).
    match = _DATE_PHRASE_RE.search(text)
    if match:
        parsed = parse_vietnamese_date_token(match.group("token"), today=today)
        if parsed is None:
            return None
        return ExtractedDate(value=parsed, span=match.span())

    # Mode 1 — year-bearing date sitting anywhere in the message.
    match = _YEAR_BEARING_DATE_RE.search(text)
    if match:
        parsed = parse_vietnamese_date_token(match.group("token"), today=today)
        if parsed is None:
            return None
        return ExtractedDate(value=parsed, span=match.span("token"))

    # Mode 2 — leading bare ``dd/mm``, disambiguated by day>12 OR month>12.
    match = _LEADING_BARE_DATE_RE.match(text)
    if match:
        day = int(match.group("d"))
        month = int(match.group("m"))
        if day > 12 or month > 12:
            parsed = parse_vietnamese_date_token(
                match.group("token"), today=today
            )
            if parsed is not None:
                return ExtractedDate(value=parsed, span=match.span("token"))

    return None


def strip_span(text: str, span: tuple[int, int]) -> str:
    """Remove the matched date phrase from ``text`` and tidy whitespace."""
    if not text or not span:
        return text
    start, end = span
    cleaned = f"{text[:start]} {text[end:]}"
    # Tidy whitespace and dangling punctuation, but preserve leading
    # ``+``/``-`` because they carry sign semantics for the amount.
    return re.sub(r"\s+", " ", cleaned).strip(" ,.;:")
