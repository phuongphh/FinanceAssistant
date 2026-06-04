"""Extract a transaction date from free-text user input.

Used by the Tier-1 NLU fast-paths so a message like
``"-1tr ăn tối ngày 16/05/2026"`` records the expense on 16/05/2026 instead
of today. Matching is anchored on Vietnamese date keywords (``ngày``, ``hôm``,
``vào ngày``) to avoid false positives — a phrase like ``"mua 12/3 phần
pizza"`` MUST NOT be re-interpreted as a date.
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

# Keyword-anchored phrases. ``ngày`` is the canonical one; ``vào ngày`` and
# ``hôm`` cover natural phrasings. We intentionally do NOT match bare
# ``16/05`` without a keyword — that risks parsing ratios/portions
# ("ăn 12/3 phần") as dates.
_DATE_PHRASE_RE = re.compile(
    rf"(?P<prefix>\b(?:vào\s+ngày|ngày|hôm))\s+(?P<token>{_DATE_TOKEN})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedDate:
    """Result of date extraction.

    ``span`` is the half-open ``(start, end)`` slice in the input text
    covering BOTH the keyword and the token, so the caller can strip the
    whole phrase from the merchant/note without leaving a dangling
    ``"ngày"``.
    """

    value: date
    span: tuple[int, int]


def extract_transaction_date(
    text: str, *, today: date | None = None
) -> ExtractedDate | None:
    """Find the first ``ngày <dd/mm[/yyyy]>``-style phrase in ``text``.

    Returns ``None`` when no recognisable date phrase is present, or when
    the captured token is malformed (e.g. ``ngày 31/02`` → invalid). The
    caller then keeps ``date.today()``.
    """
    if not text:
        return None
    match = _DATE_PHRASE_RE.search(text)
    if not match:
        return None
    parsed = parse_vietnamese_date_token(match.group("token"), today=today)
    if parsed is None:
        return None
    return ExtractedDate(value=parsed, span=match.span())


def strip_span(text: str, span: tuple[int, int]) -> str:
    """Remove the matched date phrase from ``text`` and tidy whitespace."""
    if not text or not span:
        return text
    start, end = span
    cleaned = f"{text[:start]} {text[end:]}"
    # Tidy whitespace and dangling punctuation, but preserve leading
    # ``+``/``-`` because they carry sign semantics for the amount.
    return re.sub(r"\s+", " ", cleaned).strip(" ,.;:")
