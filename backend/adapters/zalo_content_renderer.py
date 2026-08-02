"""Zalo implementation of the channel-agnostic :class:`ContentRenderer`.

Phase 5.0 implements exactly one of the four methods — :meth:`render_briefing`
— and leaves the rest raising. That asymmetry is the channel decision, not an
unfinished edge:

* **Briefing** is text. It is the one payload that survives the trip to Zalo
  intact, and the report half of the 5.0 thin slice needs it.
* **Twin view / Twin comparison** are a PNG plus a caption plus four inline
  buttons. Zalo OA has no inline keyboard in 5.0 and images need a publicly
  reachable URL, so what would arrive is a caption describing a chart the user
  cannot see and taps that do nothing. Deferred to 5.1 with the Mini App.
* **Milestone** is proactive by definition — Bé Tiền speaking first. Zalo is
  reactive-first (48h window, 8 free consulting messages), so a milestone
  either lands outside the window or spends a slot the user's next real reply
  needs. Deferred with the rest of the proactive surface.

Raising is deliberate: a renderer that quietly returned empty content would
make a dropped Twin look like a Twin with nothing in it.
"""

from __future__ import annotations

import logging
import re

from backend.adapters.zalo_notifier import strip_markdown, unwrap_button_spans
from backend.ports.content_renderer import (
    BriefingSnapshot,
    ChannelContent,
    ContentRenderer,
    MilestoneSnapshot,
    TwinComparisonSnapshot,
    TwinViewSnapshot,
)
from backend.utils.zalo_limits import ZALO_MESSAGE_MAX_CHARS

logger = logging.getLogger(__name__)

# Three or more newlines collapse to one paragraph break. Stripping markup
# empties out lines that held nothing but a ``**heading**``, and a bubble with
# a hole in it reads as broken rather than airy.
_BLANK_RUN_RE = re.compile(r"\n{3,}")

# Sentence boundary: terminal punctuation followed by whitespace. Used only
# when a single line is itself over budget, to cut between thoughts instead
# of between words.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")

_ELLIPSIS = "…"


class ZaloContentRenderer(ContentRenderer):
    """Render channel-neutral content as plain text a Zalo OA can display."""

    def render_twin_view(self, snapshot: TwinViewSnapshot) -> ChannelContent:
        # TODO(phase-5.1): needs the Mini App — chart image + tappable actions.
        raise NotImplementedError("Zalo Twin rendering is planned for Phase 5.1")

    def render_twin_comparison(
        self, snapshot: TwinComparisonSnapshot
    ) -> ChannelContent:
        # TODO(phase-5.1): needs the Mini App — chart image + tappable actions.
        raise NotImplementedError(
            "Zalo Twin comparison rendering is planned for Phase 5.1"
        )

    def render_briefing(self, snapshot: BriefingSnapshot) -> ChannelContent:
        """A briefing as plain text, fitted to the bubble.

        ``snapshot.buttons`` is dropped rather than flattened into text.
        Every briefing button is a *navigation* affordance ("Xem chi tiết",
        "Quay về Twin") whose destination is a Telegram screen; spelling one
        out on Zalo names a place the user cannot get to from here.

        The fitting happens here, not in the adapter's blind
        :func:`~backend.adapters.zalo_notifier.truncate_for_zalo`: a briefing
        ends on its recommendation, and a cut at character 300 takes the
        recommendation and keeps the preamble.
        """
        return ChannelContent(text=fit_briefing_text(snapshot.text), buttons=())

    def render_milestone(self, snapshot: MilestoneSnapshot) -> ChannelContent:
        # TODO(phase-5.1): proactive sends need the window/quota story first.
        raise NotImplementedError("Zalo milestone rendering is planned for Phase 5.1")


def fit_briefing_text(text: str, *, limit: int = ZALO_MESSAGE_MAX_CHARS) -> str:
    """Turn briefing copy into plain text that fits one Zalo bubble.

    Three passes, each reached only when the previous one is still over
    budget — so the common case (a briefing that already fits) pays for the
    markup strip and nothing else:

    1. **Whole lines.** Keep the leading lines that fit. A briefing is
       written most-important-first, so the tail is the cheapest thing to
       lose, and losing it whole leaves a message that still reads.
    2. **Sentences.** Only when the first line alone is over budget — cut
       between thoughts rather than mid-thought.
    3. **Words.** The backstop, with an ellipsis so the user can see that
       the message was clipped.

    The ≤2-emoji channel guideline is deliberately *not* enforced here.
    Emoji in a briefing carry the reading — ``⚠️`` is the difference between
    a warning and a note — so dropping the third one silently changes what
    the message says. It is a copy rule, kept by the copy that ships.
    """
    plain = _plain(text)
    if len(plain) <= limit:
        return plain

    fitted = _greedy(plain.split("\n"), "\n", limit)
    if fitted:
        return fitted

    first_line = plain.split("\n", 1)[0]
    fitted = _greedy(_SENTENCE_SPLIT_RE.split(first_line), " ", limit)
    if fitted:
        return fitted

    logger.debug("zalo.briefing.word_clipped chars=%d limit=%d", len(plain), limit)
    return _clip(plain, limit)


def _plain(text: str) -> str:
    """Strip markup and normalise the whitespace it leaves behind."""
    if not text:
        return ""
    cleaned = unwrap_button_spans(strip_markdown(text))
    cleaned = "\n".join(line.rstrip() for line in cleaned.split("\n"))
    return _BLANK_RUN_RE.sub("\n\n", cleaned).strip()


def _greedy(parts: list[str], joiner: str, limit: int) -> str:
    """Join as many leading ``parts`` as stay inside ``limit``.

    Returns ``""`` when nothing usable fits, which is the caller's signal to
    try a finer split. Blank parts are kept — they are the paragraph breaks
    — but a whitespace-only result counts as no fit, so a leading blank line
    cannot short-circuit the search.
    """
    kept: list[str] = []
    for part in parts:
        candidate = joiner.join([*kept, part])
        if len(candidate) > limit:
            break
        kept.append(part)
    return joiner.join(kept).strip()


def _clip(value: str, limit: int) -> str:
    """Cut to ``limit`` chars, backing off to a word boundary when close.

    Same rule as :mod:`backend.bot.formatters.zalo_transaction`: a mid-word
    cut reads as corruption, but backing off past half the budget loses more
    than it saves.
    """
    head = value[: limit - 1].rstrip()
    spaced = head.rsplit(" ", 1)[0]
    if len(spaced) >= limit // 2:
        head = spaced
    return head.rstrip() + _ELLIPSIS


__all__ = ["ZaloContentRenderer", "fit_briefing_text"]
