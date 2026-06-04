"""Date parsing helpers for user-facing bot inputs."""

from __future__ import annotations

import re
from datetime import date, datetime

# Vietnamese day-month-year token: ``16/05/2026``, ``16-05-2026``, ``16/05/26``
# (2-digit year) or year-less ``16/05`` / ``16-5``. We accept 1-2 digit
# day/month so ``5/3`` parses without forcing the user to zero-pad.
_DAY_MONTH = r"(?P<d>\d{1,2})[/\-.](?P<m>\d{1,2})"
_OPTIONAL_YEAR = r"(?:[/\-.](?P<y>\d{2}|\d{4}))?"

_VN_DATE_TOKEN_RE = re.compile(rf"^{_DAY_MONTH}{_OPTIONAL_YEAR}$")


def parse_vietnamese_date(value: str) -> date | None:
    """Parse dd/mm/yyyy (or dd-mm-yyyy) with ISO fallback.

    Keeps compatibility with older chats that may still show YYYY-MM-DD.
    """
    cleaned = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def parse_vietnamese_date_token(
    value: str, *, today: date | None = None
) -> date | None:
    """Parse a Vietnamese-style date token with optional year fallback.

    Accepts ``dd/mm/yyyy``, ``dd-mm-yyyy``, ``dd.mm.yyyy``, ``dd/mm/yy``
    (2-digit year → 2000+yy) and the year-less forms ``dd/mm`` / ``dd-mm``
    (year defaults to ``today.year``).

    Returns ``None`` for any malformed or out-of-range token (e.g.
    ``31/02``, ``00/05``) — callers fall back to ``date.today()``.
    """
    if not value:
        return None
    today = today or date.today()
    match = _VN_DATE_TOKEN_RE.match(value.strip())
    if not match:
        return None

    day = int(match.group("d"))
    month = int(match.group("m"))
    raw_year = match.group("y")
    if raw_year is None:
        year = today.year
    else:
        year = int(raw_year)
        if year < 100:  # ``26`` → 2026
            year += 2000

    try:
        return date(year, month, day)
    except ValueError:
        return None
