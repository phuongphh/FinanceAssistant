"""Mini App URL helpers — shared between briefing keyboard and the
``/dashboard`` command so the two entry points can't drift on path or
query-string conventions.

Returns ``None`` when ``MINIAPP_BASE_URL`` is unset (dev / first deploy
without a public host) so callers can render a placeholder instead of
a broken button. Each call site picks its own ``source`` query param —
the dashboard's analytics use it to attribute opens to the funnel that
brought the user in.
"""
from __future__ import annotations

from backend.config import get_settings


def wealth_dashboard_url(source: str) -> str | None:
    base = (get_settings().miniapp_base_url or "").rstrip("/")
    if not base:
        return None
    return f"{base}/miniapp/wealth?source={source}"
