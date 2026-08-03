"""Map transport-neutral buttons onto Zalo's button template (Phase 5.1 #3.2).

Telegram gives a button three fields — a label, a ``callback_data`` that
routes back into the bot, and an optional web-app URL. Zalo gives two
button types: ``oa.open.url`` opens a link, and ``oa.query.show`` makes
the *user* say a sentence, which comes back as an ordinary inbound text
event.

The mapping is therefore lossy, and the loss is the point of this
module. A button that cannot become a Zalo button becomes a line of text
the user can act on instead; nothing is dropped in silence. The one
exception — a button carrying neither a title nor a URL, which is not
renderable on any channel — is logged at WARNING.

The function is pure: no I/O, no settings, no clock. The Vietnamese
prose lives in ``content/zalo.yaml`` (CLAUDE.md) and reaches it through
:func:`load_button_copy`, the single seam that touches a file. Every
constant below traces to a row in the *Buttons and rich templates* table
in ``docs/conventions/zalo-operations.md`` — all of them currently
``ASSUMED``, which is why the clipping budgets are deliberately
conservative.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.ports.content_renderer import Button

logger = logging.getLogger(__name__)

# Buttons Zalo renders in one message template. `ASSUMED` — if staging
# says the real cap is lower, lower this: too high gets the whole send
# rejected, too low only demotes a button to a text line.
ZALO_MAX_BUTTONS = 5

# Our title budget, deliberately half the assumed platform limit of 100.
# Over-clipping shortens a label; under-clipping loses the message.
ZALO_BUTTON_TITLE_MAX_CHARS = 50

BUTTON_TYPE_OPEN_URL = "oa.open.url"
BUTTON_TYPE_QUERY_SHOW = "oa.query.show"

_ELLIPSIS = "…"


@dataclass(frozen=True)
class ButtonCopy:
    """Templates for the text lines that stand in for unmapped buttons.

    The defaults are punctuation, not prose, so :func:`map_buttons` stays
    pure and testable with no file access. Production overrides them from
    ``content/zalo.yaml`` via :func:`load_button_copy`.
    """

    query_line: str = "{title}"
    url_line: str = "{title}: {url}"


def load_button_copy() -> ButtonCopy:
    """Read the ``buttons`` section of ``content/zalo.yaml``.

    The only I/O in this module, and it is kept out of
    :func:`map_buttons` on purpose. A missing key degrades to the neutral
    default rather than raising — ``zalo_copy.text`` already logs the
    gap, and a send with plainer punctuation beats a crashed background
    task.
    """
    from backend.utils.zalo_copy import text

    defaults = ButtonCopy()
    return ButtonCopy(
        query_line=text("buttons", "query_line") or defaults.query_line,
        url_line=text("buttons", "url_line") or defaults.url_line,
    )


def _title(raw: str) -> str:
    """Reduce a button label to something Zalo will accept.

    Imported here rather than at module scope: ``zalo_notifier`` imports
    this module, so a top-level import would close the cycle.
    """
    from backend.adapters.zalo_notifier import strip_markdown, unwrap_button_spans

    cleaned = unwrap_button_spans(strip_markdown(raw or ""))
    # A button title is one line by definition; newlines survive
    # strip_markdown as real characters and would break the label.
    cleaned = " ".join(cleaned.split())
    if len(cleaned) <= ZALO_BUTTON_TITLE_MAX_CHARS:
        return cleaned
    return cleaned[: ZALO_BUTTON_TITLE_MAX_CHARS - 1].rstrip() + _ELLIPSIS


def _line(template: str, **fmt: str) -> str:
    """Format a suggestion line, surviving a bad template.

    Same policy as ``zalo_copy.text``: a copy edit that drops a
    placeholder must not take the channel down.
    """
    try:
        return template.format(**fmt)
    except (KeyError, IndexError, ValueError):
        logger.warning("zalo.buttons unformattable line template — falling back to title")
        return fmt.get("title") or fmt.get("url", "")


def map_buttons(
    rows: tuple[tuple[Button, ...], ...],
    *,
    copy: ButtonCopy | None = None,
    max_buttons: int = ZALO_MAX_BUTTONS,
) -> tuple[list[dict], list[str]]:
    """Split buttons into Zalo button payloads and text suggestion lines.

    Rows are flattened in reading order — Zalo has no concept of button
    rows, so a Telegram keyboard's shape is discarded but its order is
    not. The first ``max_buttons`` mappable buttons become real buttons;
    everything after them, and everything unmappable, becomes a line.

    Returns ``(buttons, lines)``. Both may be empty; neither is ever
    ``None``. Every input button appears in exactly one of the two, or
    is logged.
    """
    copy = copy or ButtonCopy()
    buttons: list[dict] = []
    lines: list[str] = []

    for button in (b for row in rows for b in row):
        title = _title(button.text)
        url = (button.web_app_url or "").strip()

        if not title and not url:
            # Nothing to render on any channel. Not silent — the epic's
            # P0 is that no button disappears without a trace.
            logger.warning(
                "zalo.buttons dropping button with no title and no url callback_data=%s",
                button.callback_data,
            )
            continue

        if url:
            if title and len(buttons) < max_buttons:
                buttons.append(
                    {
                        "title": title,
                        "type": BUTTON_TYPE_OPEN_URL,
                        "payload": {"url": url},
                    }
                )
            else:
                # A URL with no title still reaches the user as a link.
                lines.append(_line(copy.url_line, title=title or url, url=url))
            continue

        if len(buttons) < max_buttons:
            # `callback_data` cannot cross to Zalo, so the user "says"
            # the button's own label; E4's dispatcher routes that text.
            buttons.append(
                {
                    "title": title,
                    "type": BUTTON_TYPE_QUERY_SHOW,
                    "payload": {"content": title},
                }
            )
        else:
            lines.append(_line(copy.query_line, title=title))

    return buttons, lines
