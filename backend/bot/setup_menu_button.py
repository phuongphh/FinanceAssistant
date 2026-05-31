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

# Tunnel hostnames that always serve ngrok's abuse interstitial to any
# request whose User-Agent starts with ``Mozilla`` (i.e. every Telegram
# WebView on iOS / Android / Desktop). The interstitial replaces our
# dashboard HTML with a "Visit Site" warning page that the WebView either
# renders blank (mobile) or hides below the panel fold — users see a
# blank Mini App. ngrok-free has NO programmatic bypass: the only
# escape hatches are the user manually clicking "Visit Site" (sets a
# per-WebView cookie that doesn't persist across sessions) or upgrading
# to a paid plan / custom domain. We can't fix this at runtime, but we
# CAN make the failure mode loud at boot so the next person who points
# the bot at ngrok-free.dev gets a clear pointer instead of a blank
# panel mystery.
_NGROK_FREE_INTERSTITIAL_SUFFIXES = (".ngrok-free.dev", ".ngrok-free.app")


def _is_ngrok_free_interstitial_host(base_url: str) -> bool:
    """Return True if ``base_url`` will trigger ngrok's free-tier abuse
    interstitial on every Telegram WebView open.

    Hostname check only — ngrok rotates the LHS subdomain on every restart
    of a free tunnel, so we match on the suffix.
    """
    try:
        host = (urlsplit(base_url).hostname or "").lower()
    except ValueError:
        return False
    return any(host.endswith(suffix) for suffix in _NGROK_FREE_INTERSTITIAL_SUFFIXES)


def _bumped_mini_app_url(base: str, build_hash: str) -> str:
    """Return ``{base}/miniapp/wealth?b={build_hash}&source=chat_menu_button``
    preserving any existing query string or trailing slash on ``base``.

    Telegram caches WebView HTML by URL, so the build hash MUST live on the
    URL itself (not just inside the document) for the next tap to defeat the
    cache. Using a stable parameter name (``b``) means the cached entry from
    deploy N is invalidated by the new value at deploy N+1 — Telegram treats
    them as different URLs.

    The ``source`` param does double duty. Primarily it aligns this entry
    point with the ``urls.py`` convention every other launch URL already
    follows (inline "Mở dashboard" buttons carry ``&source=...``), giving us
    analytics attribution for menu-button taps. Critically, it also means the
    menu URL is NOT byte-identical to a bare ``?b=<hash>`` URL: if the WebView
    ever cached a blank/failed render of the old menu URL, ``?b`` alone cannot
    bust it on a restart that recomputes the *same* build hash (the hash only
    changes when CSS/JS/template bytes change, not on every boot). Carrying a
    distinct ``source`` yields a URL the WebView has never seen, escaping any
    poisoned cache entry — the same reason inline buttons render fine while a
    bare menu URL stays blank.
    """
    base = base.rstrip("/")
    parts = urlsplit(f"{base}/miniapp/wealth")
    existing = dict(
        kv.split("=", 1) if "=" in kv else (kv, "")
        for kv in parts.query.split("&")
        if kv
    )
    existing["b"] = build_hash
    existing["source"] = "chat_menu_button"
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

    Returns ``None`` when the bot token or ``miniapp_base_url`` aren't
    configured — dev/CI typically has no public HTTPS URL to advertise, and
    Telegram rejects ``http://`` URLs on ``web_app``. Errors don't
    propagate so a transient Telegram 5xx during deploy can't fail the
    boot — the lifespan hook still wraps in try/except, but skipping
    cleanly is the more useful default.

    Failure surfacing: every outcome is logged at WARNING or higher so it
    reaches the launchd-captured stderr log (root logger has no INFO
    handler by default, hence using WARNING for the "we acted but
    something is off" cases). Previously a Telegram 4xx response made
    ``send_telegram`` return ``None`` and this function returned silently
    — operators had no signal that the menu URL was stale until they
    tapped the button and saw a blank panel.
    """
    settings = get_settings()

    if not settings.telegram_bot_token:
        logger.warning(
            "Skipping chat menu button setup: TELEGRAM_BOT_TOKEN not configured"
        )
        return None

    if not settings.miniapp_base_url:
        logger.warning(
            "Skipping chat menu button setup: MINIAPP_BASE_URL not configured "
            "(dev/CI without public HTTPS); BotFather's manual config still applies"
        )
        return None

    if _is_ngrok_free_interstitial_host(settings.miniapp_base_url):
        # The button URL is still set so devs can poke at the panel
        # manually after clicking through the interstitial, but anyone
        # opening this from a Telegram chat will see a blank screen.
        logger.warning(
            "MINIAPP_BASE_URL=%s points at an ngrok-free tunnel — Telegram "
            "WebView will be blocked by ngrok's abuse interstitial "
            "(ERR_NGROK_6024), users see a BLANK MINI APP on chat menu "
            "button tap. Switch to a Cloudflare named tunnel (see "
            "scripts/tunnel-named-setup.sh) or upgrade to a paid ngrok "
            "plan with a custom domain. Inline-keyboard 'Mở dashboard' "
            "buttons hit the same wall — they only appear to work because "
            "Telegram caches the bypass cookie from a prior manual click.",
            settings.miniapp_base_url,
        )

    url = _bumped_mini_app_url(settings.miniapp_base_url, build_hash)
    payload = {
        "menu_button": {
            "type": "web_app",
            "text": settings.miniapp_menu_label,
            "web_app": {"url": url},
        }
    }
    result = await send_telegram("setChatMenuButton", payload)
    if result is None:
        # ``send_telegram`` already logged the HTTP status + body at ERROR,
        # but the context that would have made it actionable (which call,
        # what URL, what label) lived only in this caller's locals — so we
        # re-log it here. The bot keeps running with whatever menu button
        # BotFather has on file, which may be stale or even un-set.
        logger.error(
            "Chat menu button sync FAILED — Telegram rejected setChatMenuButton "
            "(text=%r url=%s). Users keep the previously-registered button URL "
            "until the next successful boot. Check the preceding "
            "'Telegram API error' line for the response body; common causes: "
            "URL not HTTPS, host not publicly reachable, or BUTTON_URL_INVALID "
            "from a malformed tunnel hostname.",
            settings.miniapp_menu_label,
            url,
        )
        return None
    logger.warning(
        "Chat menu button synced: text=%r url=%s",
        settings.miniapp_menu_label,
        url,
    )
    return result
