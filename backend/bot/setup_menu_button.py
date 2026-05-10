"""Sync the bot's chat menu button with Telegram on every backend startup.

# Why this exists — root-cause fix for "users see old dashboard after deploy"

Telegram Mini Apps are hosted as a WebView inside the Telegram client. The
WebView caches HTML aggressively and (per repeated field reports — most
visibly Telegram iOS / WebKit) frequently ignores ``Cache-Control: no-cache``
on the document itself. When the WebView serves a cached HTML for a deploy,
no amount of asset-side cache busting helps: the cached HTML still references
the old (un-versioned) JS bundle. The user is stuck on the old dashboard
until they manually clear Telegram's cache — not a workflow we can ask
production users to perform.

The cache key Telegram WebView uses is the **URL**. So the only reliable way
to force a fresh fetch is to give the WebView a URL it has never seen before.
The chat menu button is the dominant entry point into the Mini App; whatever
URL we register in ``setChatMenuButton`` is the URL Telegram opens when the
user taps the button.

This module re-registers the menu button on every FastAPI startup with a URL
that includes the current build hash (``?b=<git_sha>``). Each deploy →
different ``?b=`` → unique URL → cache miss → fresh HTML, **without the user
clearing anything**. The ``setMyCommands`` startup hook proved this pattern
works for slash commands; the menu button uses the exact same idiom.

# Why owning the label too

Before this module the menu label was set once via BotFather's ``/setmenubutton``
UI ("Báo cáo tài sản" — too long, truncated on narrow viewports). Now that
we're calling ``setChatMenuButton`` ourselves, the label is part of the same
payload, so we take ownership: the env-var default ``💰 Tài sản`` is short,
emoji-prefixed, and trivially overridable per environment without a code edit.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode, urlsplit, urlunsplit

from backend.config import get_settings
from backend.services.telegram_service import send_telegram

logger = logging.getLogger(__name__)


def _bumped_mini_app_url(base: str, build_hash: str) -> str:
    """Return ``{base}/miniapp/wealth?b={build_hash}`` preserving any existing
    query string or trailing slash on ``base``.

    Telegram caches WebView HTML by URL, so the build hash MUST live on the
    URL itself (not just inside the document) for the next tap to defeat the
    cache. Using a stable parameter name (``b``) means the cached entry from
    deploy N is invalidated by the new value at deploy N+1 — Telegram treats
    them as different URLs.
    """
    base = base.rstrip("/")
    parts = urlsplit(f"{base}/miniapp/wealth")
    existing = dict(
        kv.split("=", 1) if "=" in kv else (kv, "")
        for kv in parts.query.split("&")
        if kv
    )
    existing["b"] = build_hash
    new_query = urlencode(existing)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )


async def setup_chat_menu_button(build_hash: str) -> dict | None:
    """Register the global default chat menu button via ``setChatMenuButton``.

    Without ``chat_id`` Telegram applies the button as the bot-wide default,
    which is exactly what the BotFather ``/setmenubutton`` UI does — so this
    call OVERRIDES whatever was configured manually. Idempotent: calling it
    twice with identical args is a no-op on Telegram's side.

    Returns ``None`` (and logs once at INFO) when the bot token or
    ``miniapp_base_url`` aren't configured — dev/CI typically has no public
    HTTPS URL to advertise, and Telegram rejects ``http://`` URLs on
    ``web_app``. Errors don't propagate so a transient Telegram 5xx during
    deploy can't fail the boot — the lifespan hook still wraps in
    try/except, but skipping cleanly is the more useful default.
    """
    settings = get_settings()

    if not settings.telegram_bot_token:
        logger.info(
            "Skipping chat menu button setup: TELEGRAM_BOT_TOKEN not configured"
        )
        return None

    if not settings.miniapp_base_url:
        logger.info(
            "Skipping chat menu button setup: MINIAPP_BASE_URL not configured "
            "(dev/CI without public HTTPS); BotFather's manual config still applies"
        )
        return None

    url = _bumped_mini_app_url(settings.miniapp_base_url, build_hash)
    payload = {
        "menu_button": {
            "type": "web_app",
            "text": settings.miniapp_menu_label,
            "web_app": {"url": url},
        }
    }
    result = await send_telegram("setChatMenuButton", payload)
    if result is not None:
        logger.info(
            "Chat menu button synced: text=%r url=%s",
            settings.miniapp_menu_label,
            url,
        )
    return result
