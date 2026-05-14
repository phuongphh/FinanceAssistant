from __future__ import annotations

from datetime import datetime, timezone


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def humanize_vi(dt: datetime | None) -> str:
    """Return a compact Vietnamese relative timestamp for admin UX."""
    if dt is None:
        return "Chưa hoạt động"
    seconds = max(
        0, int((datetime.now(timezone.utc) - _as_aware_utc(dt)).total_seconds())
    )
    if seconds < 60:
        return "vừa xong"
    if seconds < 3600:
        return f"{seconds // 60} phút trước"
    if seconds < 86400:
        return f"{seconds // 3600} giờ trước"
    if seconds < 604800:
        return f"{seconds // 86400} ngày trước"
    return f"{seconds // 604800} tuần trước"
