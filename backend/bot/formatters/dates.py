"""Vietnamese date formatters for user-facing text.

Vietnamese convention is ``DD/MM/YYYY`` (day-first). ISO ``YYYY-MM-DD``
leaks through whenever a formatter falls back to ``str(d)``, which
reads wrong on a Vietnamese chat surface — every other handler in the
codebase already uses ``strftime("%d/%m")`` for daily lists, so this
module just centralises that into one helper instead of letting each
caller reinvent it.

Use :func:`format_date_vi_short` for in-line listings (current year
collapses to ``DD/MM`` to save horizontal space on mobile); use
:func:`format_date_vi` for headings or anything cross-year where the
year matters.
"""
from __future__ import annotations

from datetime import date, datetime


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def format_date_vi(value: date | datetime) -> str:
    """Return ``DD/MM/YYYY`` — the canonical Vietnamese date form."""
    return _as_date(value).strftime("%d/%m/%Y")


def format_date_vi_short(
    value: date | datetime, *, ref_date: date | None = None
) -> str:
    """Return ``DD/MM`` when ``value`` shares the year with ``ref_date``,
    otherwise ``DD/MM/YYYY``.

    ``ref_date`` defaults to ``date.today()`` (system date). Callers
    that need Vietnam-local "today" should pass it explicitly via
    ``time_vn.now_vn().date()`` to avoid timezone drift on UTC servers.
    """
    d = _as_date(value)
    ref = ref_date if ref_date is not None else date.today()
    if d.year == ref.year:
        return d.strftime("%d/%m")
    return d.strftime("%d/%m/%Y")
