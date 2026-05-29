"""Vietnam-time helpers — single source of truth for user-facing timestamps.

Every timestamp shown to a user must read in Vietnam local time (UTC+7,
``Asia/Ho_Chi_Minh``, no DST). Historically each call site rolled its own
conversion and several drifted:

- ``datetime.now()`` returns *naive system-local* time — on a UTC prod
  server that renders as UTC, one hour shy of seven off VN.
- A bare ``dt.astimezone()`` (no argument) also resolves to *system-local*,
  so a UTC-aware DB value stays UTC instead of shifting to +7.

Both look correct on a developer laptop in ICT and silently wrong in
production. Route every display path through the helpers here so the bug
cannot reappear:

- :func:`now_vn` for "current time" displays (chart watermarks, report
  timestamps) instead of ``datetime.now()``.
- :func:`to_vn` to convert a stored timestamp (naive=UTC or aware) to VN
  instead of a bare ``.astimezone()``.
- :func:`format_vn` for the common convert-then-strftime in one call.

Storage code (DB writes) should keep using ``datetime.utcnow`` — asyncpg
treats naive values as UTC on insert, so the instant round-trips intact;
these helpers are for *rendering*, not persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_vn() -> datetime:
    """Current wall-clock time in Vietnam (aware, UTC+7)."""
    return datetime.now(VN_TZ)


def to_vn(dt: datetime | None) -> datetime | None:
    """Convert any timestamp to Vietnam time for display.

    Naive datetimes are assumed UTC (the historical default of
    ``datetime.utcnow``); aware datetimes are shifted to ``Asia/Ho_Chi_Minh``.
    Returns ``None`` unchanged so callers can format defensively.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ)


def format_vn(dt: datetime | None, fmt: str, *, default: str = "") -> str:
    """Convert ``dt`` to VN time and ``strftime`` it, with a null fallback."""
    vn = to_vn(dt)
    if vn is None:
        return default
    return vn.strftime(fmt)
