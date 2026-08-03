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
from backend.utils.zalo_limits import ZALO_MESSAGE_MAX_CHARS

logger = logging.getLogger(__name__)

# Practical display limit. Spec: 300 chars (Story #439). Defined in
# ``backend.utils.zalo_limits`` and re-exported here: this module
# *enforces* it, but the Zalo formatters need the same number to compose
# within it, and they must not import this adapter (see that module).
__all__ = [
    "ZALO_MESSAGE_MAX_CHARS",
    "ZaloNotifier",
    "strip_markdown",
    "truncate_for_zalo",
    "unwrap_button_spans",
]

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
# A bare ``[Xem chi tiết]`` span — how the shared Telegram copy marks up an
# inline button. Deliberately *not* folded into ``strip_markdown``: that
# function is the Markdown/HTML translator, and a bare bracket span is not
# markup, it is a Telegram affordance that Zalo has no equivalent for.
_BUTTON_SPAN_RE = re.compile(r"\[([^\[\]\n]+)\]")


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


def unwrap_button_spans(text: str) -> str:
    """Turn ``[Label]`` inline-button markup into plain words.

    Zalo OA has no inline keyboard in 5.0, so a surviving bracket span
    reads as a control the user will try to tap and nothing will happen.
    Unwrap rather than delete: the label often carries the only verb in
    the sentence (``[Xem báo cáo]`` → ``Xem báo cáo``), so removing the
    span outright can leave a dangling line.

    **Run this after :func:`strip_markdown`, never before.** A Markdown
    link is ``[label](url)`` — unwrapping its brackets first destroys the
    shape ``strip_markdown`` matches on, and the URL then survives into
    the bubble as ``label(https://…)``.

    Whitespace policy is left to the caller: the inbound handler collapses
    the gap two adjacent buttons leave behind, while a briefing keeps its
    paragraph breaks.
    """
    if not text:
        return ""
    # Repeat to a fixed point. One pass turns "[[A]]" into "[A]" — the
    # inner span matches, the outer pair is left orphaned — and shipping a
    # bracket is the exact thing this function exists to prevent. Each
    # pass removes at least two characters, so this terminates; in the
    # ordinary no-nesting case it costs one extra regex scan and makes the
    # function idempotent, which both callers rely on since the notifier
    # sanitises again downstream.
    while True:
        unwrapped = _BUTTON_SPAN_RE.sub(r"\1", text)
        if unwrapped == text:
            return text
        text = unwrapped


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

    @property
    def is_configured(self) -> bool:
        """Whether this server has any credential to send with.

        Forwarded from the client so callers holding only a notifier —
        :class:`~backend.adapters.zalo_window_notifier.WindowedZaloNotifier`
        does — can skip work that is certain to fail. Optimistic, like the
        client's own: it says a token *can be obtained*, not that Zalo will
        accept it.
        """
        return self._client.is_configured

    async def send_message(
        self,
        chat_id: int,  # noqa: ARG002 — Notifier port signature
        text: str,
        *,
        parse_mode: str | None = None,  # noqa: ARG002 — Zalo ignores parse_mode
        reply_markup: dict | None = None,  # noqa: ARG002 — Telegram wire format; see `buttons`
        **kwargs: Any,
    ) -> dict | None:
        """Send a plain-text message to the bound Zalo user.

        Returns a minimal dict on success (so callers can branch on
        truthiness like the Telegram path) or ``None`` when the request
        never reached Zalo.

        :class:`~backend.adapters.zalo_oa.ZaloSendRejected` is allowed to
        propagate rather than being collapsed into ``None``: only the
        window notifier that wraps this one can act on the distinction
        (refund the reserved slot vs. keep it), and swallowing it here
        would throw that information away one layer too early. The
        ``Notifier`` port's "implementations do not raise" contract still
        holds for callers, because :func:`~backend.adapters.
        zalo_window_notifier.build_zalo_notifier` is the only sanctioned
        way to construct a Zalo notifier and it always wraps.

        ``buttons`` (Phase 5.1 #3.3) is a channel-neutral
        ``tuple[tuple[Button, ...], ...]`` straight off
        :class:`~backend.ports.content_renderer.ChannelContent` — not
        Telegram's ``reply_markup`` wire format, which this adapter must
        never have to parse. Buttons that cannot become Zalo buttons come
        back as text lines and are appended *before* the character check,
        so the 300-char ceiling is applied to what the user actually
        sees.
        """
        # Imported inside the method: zalo_button_mapper reaches back
        # into this module for strip_markdown/unwrap_button_spans, so a
        # module-scope import here would close the cycle.
        from backend.adapters.zalo_button_mapper import load_button_copy, map_buttons

        rows = kwargs.get("buttons") or ()
        zalo_buttons, suggestion_lines = (
            map_buttons(rows, copy=load_button_copy()) if rows else ([], [])
        )

        plain = strip_markdown(text)
        if suggestion_lines:
            plain = "\n".join([plain, *suggestion_lines]) if plain else "\n".join(suggestion_lines)
        body = truncate_for_zalo(plain)
        if not body:
            return None

        if zalo_buttons:
            ok = await self._client.send_message_with_buttons(
                self._zalo_user_id, body, zalo_buttons
            )
        else:
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

        if kwargs.get("buttons"):
            # Zalo puts an image and a button stack in the same
            # ``message.attachment`` slot, so one send cannot carry both
            # (runbook → Buttons and rich templates). Splitting it into
            # two sends costs a second slot out of the 48h window's
            # eight, which is a product call E2 owns, not one this
            # adapter should make on its own. Loud, not silent.
            logger.warning(
                "ZaloNotifier.send_photo received buttons — dropped: "
                "Zalo cannot render an image and a button template in one message"
            )

        plain_caption = truncate_for_zalo(strip_markdown(caption), limit=100)
        ok = await self._client.send_image_message(
            self._zalo_user_id, image_url, plain_caption
        )
        if not ok:
            return None
        return {"ok": True, "channel": self.channel}
