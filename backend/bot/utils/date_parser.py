"""Date parsing helpers for user-facing bot inputs."""

from __future__ import annotations

from datetime import date, datetime


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
