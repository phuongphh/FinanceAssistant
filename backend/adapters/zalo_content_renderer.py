"""Zalo implementation of the channel-agnostic :class:`ContentRenderer`.

Phase 5.0 shipped :meth:`render_briefing` alone; Phase 5.1 #2.2/#2.3 fills in
the other three now that E1 gives images a public URL and E3 gives buttons a
mapping. The four methods answer the same questions the Telegram renderer
does, from a bubble a tenth the size, so the shape of each answer differs:

* **Briefing** is text, and survives the trip intact.
* **Twin view / Twin comparison** keep the chart — E1 publishes the bytes, so
  a Zalo user sees the same picture — but the caption is rebuilt from
  ``content/zalo.yaml`` rather than cut down from Telegram's. Telegram's
  caption carries a narrative, three weather cards and a present anchor; none
  of that fits, and a truncation of it would end mid-sentence on whichever
  clause happened to sit at character 300.
* **Milestone** says what was reached and what it changed in the Twin. It
  stays *reactive*: this renders a milestone, it does not decide to send one
  — the 48h window and the 8-message quota still gate that, in
  :mod:`backend.adapters.zalo_window_notifier`.

Buttons come back empty from all four. A Zalo message carries an image or
buttons, not both (see ``docs/conventions/zalo-operations.md``), the Twin
carries the image, and Telegram's Twin buttons name Telegram screens. E4 #4.1
owns re-enabling them once the dispatcher can route the text an
``oa.query.show`` tap produces.

Nothing here reads copy from code: every user-visible string is a
``content/zalo.yaml`` lookup, and every one is written short at source rather
than cut to length. The renderer's own job is to choose *which* lines fit,
never to cut one in half.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from backend.adapters.zalo_notifier import strip_markdown, unwrap_button_spans
from backend.bot.formatters.money import format_money_short
from backend.ports.content_renderer import (
    BriefingSnapshot,
    ChannelContent,
    ContentRenderer,
    MilestoneSnapshot,
    TwinComparisonSnapshot,
    TwinViewSnapshot,
)
from backend.twin.services.twin_chart_service import render_projection_chart
from backend.utils.zalo_copy import text as copy_text
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

# Ceiling for a value the caller hands us to drop into a copy line — an
# action suggestion, a milestone title, a Twin effect. These come from
# surfaces written for Telegram and can run long; without a bound, one of
# them alone eats the bubble and every following line is dropped. 120 leaves
# room for a headline and one more line either side.
_INLINE_VALUE_MAX_CHARS = 120


class ZaloContentRenderer(ContentRenderer):
    """Render channel-neutral content as plain text a Zalo OA can display.

    ``chart_renderer`` is injected with the real one as its default, the same
    seam :class:`~backend.adapters.telegram_content_renderer.TelegramContentRenderer`
    uses: it keeps this class pure at unit-test time without a flag.
    """

    def __init__(
        self,
        chart_renderer: Callable[..., bytes] = render_projection_chart,
    ) -> None:
        self._chart_renderer = chart_renderer

    def render_twin_view(self, snapshot: TwinViewSnapshot) -> ChannelContent:
        """The Twin cone as one bubble: where the numbers land, and the caveat.

        Composed from bounded inputs only — the salutation, the year, and
        three ``format_money_short`` figures. ``user_name``, ``narrative``,
        ``present_anchor`` and the scenario cards are deliberately left out:
        each is unbounded, and any one of them could push the disclaimer off
        the end. On Zalo the pronoun does the work the name does on Telegram.
        """
        fmt = _copy_args(snapshot.salutation, target_year=snapshot.target_year)
        lines = [
            copy_text("twin", "headline", **fmt),
            copy_text(
                "twin",
                "range_line",
                p10=format_money_short(snapshot.p10),
                p50=format_money_short(snapshot.p50),
                p90=format_money_short(snapshot.p90),
                **fmt,
            ),
            copy_text("twin", "stale_note", **fmt) if snapshot.is_stale else "",
            copy_text("twin", "note", **fmt),
        ]
        return self._with_chart(
            _fit_lines(lines),
            snapshot.cone,
            snapshot.optimal_cone,
            snapshot.filename,
        )

    def render_twin_comparison(
        self, snapshot: TwinComparisonSnapshot
    ) -> ChannelContent:
        """Current vs optimal: the gap, and the one action that closes most of it.

        ``snapshot.actions`` is a multi-line block on Telegram. Only its first
        line survives here — the lines are already ordered by impact, and a
        list of three inside a 300-character bubble crowds out the number the
        list is about.
        """
        fmt = _copy_args(snapshot.salutation, target_year=snapshot.target_year)
        lines = [
            copy_text("twin_comparison", "headline", **fmt),
            copy_text(
                "twin_comparison",
                "delta_line",
                current=format_money_short(snapshot.current_p50),
                optimal=format_money_short(snapshot.optimal_p50),
                delta=snapshot.delta_pct,
                **fmt,
            ),
            _action_line(snapshot.actions, fmt),
            copy_text("twin_comparison", "note", **fmt),
        ]
        return self._with_chart(
            _fit_lines(lines),
            snapshot.current_cone,
            snapshot.optimal_cone,
            snapshot.filename,
        )

    def _with_chart(
        self,
        body: str,
        cone: list[dict[str, Any]],
        optimal: list[dict[str, Any]] | None,
        filename: str,
    ) -> ChannelContent:
        """Attach the projection chart, or ship the text alone if it fails.

        Downgrading rather than raising is the Zalo-specific call. On Telegram
        the chart *is* the message and a failure should be loud; here the
        numbers are already spelled out in the text above it, so a user who
        gets the bubble without the picture has still been answered.

        The bytes stay bytes. Turning them into a URL is #2.4's job in the
        notifier — a renderer that knew about the media service would be a
        renderer that needs a database session.
        """
        images: tuple[bytes, ...] = ()
        if cone:
            try:
                images = (self._chart_renderer(cone, optimal=optimal),)
            except Exception:
                logger.warning("zalo.twin.chart_failed", exc_info=True)
        return ChannelContent(
            text=body,
            images=images,
            buttons=(),
            filename=filename if images else None,
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
        """A milestone in three short lines: what was reached, what it changed.

        Prefers the structured ``title``/``effect`` and falls back to fitting
        the pre-composed ``text``. The fallback is not the good path — it
        yields whatever the calling surface wrote for a bigger screen — but a
        milestone that renders imperfectly beats one that raises on a caller
        that has not been taught the new fields yet.

        The copy never compares the user to anyone or mentions how long the
        milestone took; ``tests/test_phase_5_1/test_zalo_copy.py`` holds that
        line, because it is a persona rule and persona rules die in code.
        """
        title = _inline(snapshot.title)
        if not title:
            return ChannelContent(text=fit_briefing_text(snapshot.text), buttons=())

        fmt = _copy_args(snapshot.salutation)
        effect = _inline(snapshot.effect)
        lines = [
            copy_text("milestone", "headline", title=title, **fmt),
            copy_text("milestone", "twin_effect", effect=effect, **fmt) if effect else "",
            copy_text("milestone", "closing", **fmt),
        ]
        return ChannelContent(text=_fit_lines(lines), buttons=())


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


def _copy_args(salutation: str, **extra: Any) -> dict[str, Any]:
    """The two salutation keys every parity line may use, plus caller extras.

    ``content/zalo.yaml`` templates carry ``{salutation}`` mid-sentence and
    ``{Salutation}`` at the start of one, so both are always supplied:
    :func:`~backend.utils.zalo_copy.text` returns the *raw template* when a
    key is missing, which would put a literal brace in front of the user.
    """
    value = (salutation or "").strip() or "bạn"
    return {"salutation": value, "Salutation": value.capitalize(), **extra}


def _inline(value: str) -> str:
    """Make a caller-supplied value safe to drop into one line of copy."""
    flat = " ".join(_plain(value).split())
    if len(flat) > _INLINE_VALUE_MAX_CHARS:
        flat = _clip(flat, _INLINE_VALUE_MAX_CHARS)
    return flat


def _action_line(actions: str, fmt: dict[str, Any]) -> str:
    """The first suggested action, as one copy line — or nothing."""
    first = next((line for line in _plain(actions).split("\n") if line.strip()), "")
    if not first:
        return ""
    return copy_text("twin_comparison", "actions_lead", actions=_inline(first), **fmt)


def _fit_lines(lines: list[str], *, limit: int = ZALO_MESSAGE_MAX_CHARS) -> str:
    """Join copy lines top-down, dropping from the tail until they fit.

    The lines arrive in priority order and each says one whole thing, so
    dropping the last one loses the least — which is why the copy was written
    as separate lines in the first place. Nothing is ever cut mid-sentence
    here; :func:`_clip` is reached only when a *single* line is over budget,
    which would be a copy bug rather than a fitting decision.

    Empty entries are filtered before joining: a
    :func:`~backend.utils.zalo_copy.text` miss returns ``""``, and joining it
    would leave a blank line the user reads as a missing paragraph.
    """
    usable = [line.strip() for line in lines if line and line.strip()]
    if not usable:
        return ""

    joined = "\n".join(usable)
    if len(joined) <= limit:
        return joined

    logger.debug("zalo.copy.line_dropped lines=%d chars=%d", len(usable), len(joined))
    return _greedy(usable, "\n", limit) or _clip(usable[0], limit)


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
