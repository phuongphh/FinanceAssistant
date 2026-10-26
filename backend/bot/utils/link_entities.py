"""Markdown-style links → Telegram ``text_link`` entities.

Renderers (e.g. the morning briefing) emit links as ``[title](url)`` so the
copy stays readable in tests and non-Telegram consumers. Briefings are sent
as plain text with explicit ``entities`` (custom emoji, Phase 3.9.5), where
Telegram ignores ``parse_mode`` — so links are converted to ``text_link``
entities at the transport boundary instead of relying on a Markdown parser.
This also means titles never need user-visible ``\\`` escapes.
"""
from __future__ import annotations

import re
from typing import Any

from backend.bot.utils.emoji_animation import MessageEntity, _utf16_len, render_context

# Title: any run of escaped chars or chars other than ``\`` / ``]``.
# URL: http(s) only, no whitespace / ``)`` (``)`` is percent-encoded on build).
_LINK_RE = re.compile(r"\[((?:\\.|[^\\\]])+)\]\((https?://[^\s)]+)\)")
_TITLE_UNESCAPE_RE = re.compile(r"\\(.)")


def markdown_link(title: str, url: str | None) -> str:
    """Build ``[title](url)`` that :func:`extract_link_entities` round-trips.

    Falls back to the bare title when ``url`` is not an http(s) URL, so a bad
    feed row never renders a broken link.
    """
    clean_title = " ".join(str(title or "").split())
    clean_url = str(url or "").strip()
    if not clean_title or not re.match(r"https?://", clean_url):
        return clean_title
    escaped_title = re.sub(r"([\\\[\]])", r"\\\1", clean_title)
    escaped_url = clean_url.replace(" ", "%20").replace(")", "%29")
    return f"[{escaped_title}]({escaped_url})"


def extract_link_entities(text: str) -> tuple[str, list[MessageEntity]]:
    """Strip ``[title](url)`` markup and return ``text_link`` entities.

    Offsets/lengths use Telegram's UTF-16 code-unit indexing.
    """
    if not text or "](" not in text:
        return text, []

    parts: list[str] = []
    entities: list[MessageEntity] = []
    utf16_offset = 0
    cursor = 0
    for match in _LINK_RE.finditer(text):
        before = text[cursor:match.start()]
        parts.append(before)
        utf16_offset += _utf16_len(before)

        title = _TITLE_UNESCAPE_RE.sub(r"\1", match.group(1))
        length = _utf16_len(title)
        entities.append(
            {"type": "text_link", "offset": utf16_offset, "length": length, "url": match.group(2)}
        )
        parts.append(title)
        utf16_offset += length
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts), entities


def telegram_text_and_kwargs(text: str, context: str) -> tuple[str, dict[str, Any]]:
    """Return plain ``text`` plus send kwargs carrying link + custom-emoji entities.

    Mirrors :func:`message_kwargs_for_animation`: an empty dict when there is
    nothing to annotate, so the default send path is unchanged.
    """
    plain, link_entities = extract_link_entities(text)
    _, emoji_entities = render_context(plain, context)
    entities = sorted([*link_entities, *emoji_entities], key=lambda e: e["offset"])
    return plain, ({"entities": entities} if entities else {})


__all__ = [
    "extract_link_entities",
    "markdown_link",
    "telegram_text_and_kwargs",
]
