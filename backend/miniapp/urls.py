"""Mini App URL helpers — shared between briefing keyboard and the
``/dashboard`` command so the two entry points can't drift on path or
query-string conventions.

Every URL is emitted with a ``?b=<build_hash>`` query param so Telegram's
WebView treats each deploy as a never-before-seen URL and bypasses its
HTML cache. Without this, repeated taps on the same inline button (e.g.,
the briefing "Mở Dashboard" button) keep serving the previous deploy's
HTML because Telegram caches by URL and ``?source=briefing`` alone is
constant across deploys. The chat-menu-button cache-bust in
``backend/bot/setup_menu_button.py`` uses the same ``?b=`` convention.

Returns ``None`` when ``MINIAPP_BASE_URL`` is unset (dev / first deploy
without a public host) so callers can render a placeholder instead of
a broken button. Each call site picks its own ``source`` query param —
the dashboard's analytics use it to attribute opens to the funnel that
brought the user in.
"""
from __future__ import annotations

from urllib.parse import urlencode

from backend.config import get_settings


def _miniapp_url(path: str, *, source: str) -> str | None:
    base = (get_settings().miniapp_base_url or "").rstrip("/")
    if not base:
        return None
    # Import lazily so this helper module stays importable in contexts
    # that don't initialise the FastAPI app (e.g., bare unit tests).
    from backend.miniapp.routes import current_build_hash

    query = urlencode({"b": current_build_hash(), "source": source})
    return f"{base}{path}?{query}"


def wealth_dashboard_url(source: str) -> str | None:
    return _miniapp_url("/miniapp/wealth", source=source)


def twin_dashboard_url(source: str) -> str | None:
    return _miniapp_url("/miniapp/twin", source=source)


def cashflow_dashboard_url(source: str) -> str | None:
    return _miniapp_url("/miniapp/cashflow", source=source)
