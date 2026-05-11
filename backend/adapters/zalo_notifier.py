"""Zalo implementation of the :class:`Notifier` port.

Phase 4B Epic 4 (Story P4B-S22).

Differences from :class:`TelegramNotifier`:
- Zalo does NOT render Markdown — we strip ``*``, ``_``, ``` ` ```,
  Markdown links, and HTML tags before sending so users don't see raw
  asterisks.
- Zalo's CS message limit is ~2000 chars but practical display
  truncates around 300 chars on mobile (Story spec). We hard-cap at
  300 to keep alerts scannable; longer content should be a Zalo
  template message (out of scope for Phase 4B Epic 4).

Notifier port contract: never raise from public methods, return
``None`` on failure so the caller can choose retry policy.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.adapters.zalo_oa import ZaloOAClient

logger = logging.getLogger(__name__)

# Practical display limit. Spec: 300 chars (Story #439).
ZALO_MESSAGE_MAX_CHARS = 300

# Markdown/HTML strippers — order matters: HTML tags first so we don't
# leave dangling angle-brackets; then markdown emphasis; then collapse
# leftover whitespace from removed tokens.
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# Inline code spans / triple-backtick blocks. We keep the content,
# strip only the fence characters.
_CODE_FENCE_RE = re.compile(r"```([^`]*)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
# Markdown links — keep the visible label, drop the URL.
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
# Bold / italic / strikethrough markers — drop the marker characters.
_MD_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|~~)")
# Telegram-style escape backslashes before punctuation.
_TG_ESCAPE_RE = re.compile(r"\\([_*\[\]\(\)~`>#+\-=|{}.!])")
# Repeated whitespace.
_WS_RE = re.compile(r"[ \t]{2,}")


def strip_markdown(text: str) -> str:
    """Convert Markdown/HTML-flavoured text to plain Zalo-safe text.

    Idempotent: ``strip_markdown(strip_markdown(x)) == strip_markdown(x)``.
    """
    if not text:
        return ""

    # 1. HTML tags (Telegram alert path uses parse_mode=HTML).
    cleaned = _HTML_TAG_RE.sub("", text)

    # 2. Code fences — preserve inner text, drop backticks.
    cleaned = _CODE_FENCE_RE.sub(r"\1", cleaned)
    cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)

    # 3. Markdown links — keep label.
    cleaned = _MD_LINK_RE.sub(r"\1", cleaned)

    # 4. Telegram MarkdownV2 backslash escapes — drop the backslash.
    cleaned = _TG_ESCAPE_RE.sub(r"\1", cleaned)

    # 5. Bold / italic / strike markers — drop the marker chars.
    cleaned = _MD_EMPHASIS_RE.sub("", cleaned)

    # 6. Collapse intra-line whitespace runs (don't touch newlines so
    #    multi-line alerts keep their structure).
    cleaned = _WS_RE.sub(" ", cleaned)

    return cleaned.strip()


def truncate_for_zalo(text: str, limit: int = ZALO_MESSAGE_MAX_CHARS) -> str:
    """Cap message length at ``limit`` chars. Adds an ellipsis when
    truncation happens so the user knows the message was clipped."""
    if len(text) <= limit:
        return text
    # Leave room for the ellipsis itself.
    return text[: limit - 1].rstrip() + "…"


class ZaloNotifier:
    """Send messages to a single Zalo OA-followed user.

    Bound to one Zalo user_id at construction so the call surface
    matches :class:`Notifier` (which takes a ``chat_id``; we ignore
    the int and use the bound Zalo user_id). The cashflow fan-out
    constructs one notifier per linked user — this is the cleanest
    way to keep ``Notifier`` channel-agnostic.
    """

    channel = "zalo"

    def __init__(self, client: ZaloOAClient, zalo_user_id: str):
        self._client = client
        self._zalo_user_id = zalo_user_id

    async def send_message(
        self,
        chat_id: int,  # noqa: ARG002 — Notifier port signature
        text: str,
        *,
        parse_mode: str | None = None,  # noqa: ARG002 — Zalo ignores parse_mode
        reply_markup: dict | None = None,  # noqa: ARG002 — Zalo has no inline keyboards
        **kwargs: Any,  # noqa: ARG002 — swallow extra Telegram-specific kwargs
    ) -> dict | None:
        """Send a plain-text message to the bound Zalo user.

        Returns a minimal dict on success (so callers can branch on
        truthiness like the Telegram path) or ``None`` on failure.
        """
        plain = strip_markdown(text)
        body = truncate_for_zalo(plain)
        if not body:
            return None

        ok = await self._client.send_message(self._zalo_user_id, body)
        if not ok:
            return None
        return {"ok": True, "channel": self.channel}

    async def send_photo(
        self,
        chat_id: int,  # noqa: ARG002 — Notifier port signature
        photo: bytes,  # noqa: ARG002 — Zalo OA requires a URL, not raw bytes
        *,
        caption: str = "",
        reply_markup: dict | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> dict | None:
        """Photo support is intentionally minimal for Phase 4B Epic 4.

        The Zalo OA endpoint takes a public ``image_url`` rather than
        raw bytes, and Phase 4B Epic 4 ships only the cashflow alert
        (text-only). We accept the call so the Notifier contract holds
        but log a warning if anyone actually tries to send an image
        via Zalo — they'll need a later phase to add asset upload.
        """
        image_url = kwargs.get("image_url")
        if not image_url:
            logger.warning(
                "ZaloNotifier.send_photo called without image_url — "
                "falling back to caption-only text send"
            )
            if caption:
                return await self.send_message(0, caption)
            return None

        plain_caption = truncate_for_zalo(strip_markdown(caption), limit=100)
        ok = await self._client.send_image_message(
            self._zalo_user_id, image_url, plain_caption
        )
        if not ok:
            return None
        return {"ok": True, "channel": self.channel}
