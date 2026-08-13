"""Plain-text transaction confirmations for Zalo (Phase 5.0 #2.4).

The Telegram card is HTML, carries a progress bar, a category emoji per
row and four inline buttons. None of that survives the trip to Zalo: the
OA API renders plain text only, cuts the bubble at ~300 characters, and
has no inline keyboard in 5.0. Reusing
:func:`backend.bot.formatters.templates.format_transaction_confirmation`
and stripping it down afterwards would mean the user reads the *residue*
of a Telegram card — orphaned separators, a truncated budget bar, a hint
pointing at buttons that aren't there.

So this module renders the same facts natively for the channel: what was
recorded, how much, which category. Every string comes from the
``capture`` section of ``content/zalo.yaml``; the only thing composed
here is the order of the lines.

Two channel constraints shape the output and are worth stating because
they are easy to break by accident:

* **≤ 2 emoji per message.** The header spends the budget on ``✅``, so
  category emoji are dropped and the category name is written out.
* **~300 display characters.** The batch renderer fits itself to that
  budget instead of trusting a row count: it composes the trailing rows
  first and then adds as many item rows as still fit. The adapter's
  truncation is blind — it would cut the list mid-item and take the
  hint with it — so the goal here is that it never fires at all.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.config.categories import get_category
from backend.utils.zalo_copy import text as zalo_text
from backend.utils.zalo_limits import ZALO_MESSAGE_MAX_CHARS

# Upper bound on listed rows, applied before the character budget below.
# A batch of thirty tiny amounts would technically fit but reads as a
# wall; five rows plus "và N khoản nữa" is the shape we want, and the
# budget only ever shortens it further.
MAX_BATCH_ITEMS = 5

# Merchant names are free text. Past roughly this width a single row
# eats the space two rows would have used, and the batch stops being a
# list. Clipped rather than dropped: the leading words are what make a
# row recognisable.
MAX_BATCH_MERCHANT_CHARS = 28

# A single transaction has the bubble to itself, so it can afford a
# fuller name — this bound only exists so a pasted paragraph cannot
# push the date, source and hint rows out of the message.
MAX_MERCHANT_CHARS = 60

_ELLIPSIS = "…"


def _capture(key: str, **fmt) -> str:
    return zalo_text("capture", key, **fmt)


def _clean(value: str | None, *, fallback: str = "Giao dịch") -> str:
    """Collapse a user-supplied label into one safe single-line token.

    Merchant names come from free text the user typed. A newline in one
    would break the line structure the batch renderer depends on, and no
    escaping is possible on a plain-text channel — so flatten instead.
    """
    if not value:
        return fallback
    collapsed = " ".join(value.split())
    return collapsed or fallback


def _clip(value: str, limit: int) -> str:
    """Bound a label's width, ending on a word where one is available.

    Cutting mid-word reads as corruption rather than as an abbreviation,
    so we back off to the last space when that keeps most of the label.
    """
    if len(value) <= limit:
        return value
    head = value[: limit - 1].rstrip()
    spaced = head.rsplit(" ", 1)[0]
    if len(spaced) >= limit // 2:
        head = spaced
    return head + _ELLIPSIS


def format_zalo_transaction(
    *,
    merchant: str | None,
    amount,
    category_code: str,
    transaction_type: str = "expense",
    expense_date: date | None = None,
    source_label: str | None = None,
    show_edit_hint: bool = False,
) -> str:
    """One recorded transaction, as Zalo will actually display it.

    ``amount`` is formatted in full (``45,000đ``) rather than shortened:
    this is the receipt for something the user just told us, and a
    rounded "45k" invites a second guess about what was stored.
    """
    key = "money_in" if transaction_type == "money_in" else "expense"
    lines = [
        _capture(
            key,
            merchant=_clip(_clean(merchant), MAX_MERCHANT_CHARS),
            amount=format_money_full(amount),
            category=get_category(category_code).name_vi,
        ),
        *_tail_lines(
            expense_date=expense_date,
            source_label=source_label,
            show_edit_hint=show_edit_hint,
        ),
    ]
    return "\n".join(line for line in lines if line)


def _tail_lines(
    *,
    expense_date: date | None,
    source_label: str | None,
    show_edit_hint: bool,
) -> list[str]:
    """The optional rows that close both message shapes.

    Date, then source, then hint — that order is what makes the bubble
    scannable, and it is shared so the two formatters cannot drift apart.
    """
    lines: list[str] = []

    # Same rule as the Telegram card: only mention the date when the user
    # pinned a different day. On today's transactions it is pure noise,
    # and noise is expensive inside a 300-character bubble.
    if expense_date is not None and expense_date != date.today():
        lines.append(_capture("date_line", date=expense_date.strftime("%d/%m/%Y")))

    if source_label:
        lines.append(_capture("source_line", source=_clean(source_label, fallback="")))

    if show_edit_hint:
        lines.append(_capture("edit_hint"))

    return [line for line in lines if line]


def format_zalo_transaction_batch(
    *,
    items: list[tuple[str | None, object, str]],
    expense_date: date | None = None,
    source_label: str | None = None,
    show_edit_hint: bool = False,
) -> str:
    """Several transactions recorded from one message.

    ``items`` is ``(merchant, amount, category_code)`` — the same tuple
    the Telegram batch formatter takes, so a caller can hand the identical
    list to either channel.

    Per-item amounts are shortened (``45k``) while the total is written in
    full: the total is the number the user checks, the individual rows are
    there to confirm nothing was missed or invented.

    How many rows are actually listed depends on how wide they turn out
    to be, not on a fixed count — see :func:`_fit`. The header, the total
    and the trailing rows are never the thing that gets dropped, because
    they are the part the user is checking.
    """
    if not items:
        return ""

    total = sum((_as_decimal(amount) for _, amount, _ in items), start=Decimal(0))
    header = _capture("batch_header", count=len(items), total=format_money_full(total))
    rows = [
        _capture(
            "batch_item",
            merchant=_clip(_clean(merchant), MAX_BATCH_MERCHANT_CHARS),
            amount=format_money_short(amount),
        )
        for merchant, amount, _category in items[:MAX_BATCH_ITEMS]
    ]
    tail = _tail_lines(
        expense_date=expense_date,
        source_label=source_label,
        show_edit_hint=show_edit_hint,
    )
    return _fit(header=header, rows=rows, tail=tail, total_items=len(items))


def _fit(*, header: str, rows: list[str], tail: list[str], total_items: int) -> str:
    """Assemble the batch so it lands inside the display limit.

    A fixed row count cannot hold the ceiling: five rows of ``"- Phở
    45k"`` are a third of the bubble, five rows of a restaurant's full
    registered name are past it. So the parts that must survive — header,
    "và N khoản nữa", date, source, hint — are assembled first, and item
    rows are added only while the whole message still fits.

    Dropping a row changes the "và N khoản nữa" count, which changes the
    length, so the line is recomputed on each attempt rather than
    measured once up front.
    """
    shown = len(rows)
    while True:
        remaining = total_items - shown
        more = [_capture("batch_more", count=remaining)] if remaining > 0 else []
        body = "\n".join([header, *rows[:shown], *more, *tail])
        if shown == 0 or len(body) <= ZALO_MESSAGE_MAX_CHARS:
            # ``shown == 0`` means even the header and the trailing rows
            # overflow on their own — copy the code ships, not user data,
            # so it cannot happen with the current strings, and leaving
            # the adapter to truncate beats looping forever.
            return body
        shown -= 1


def _as_decimal(value) -> Decimal:
    """Normalise one item's amount before summing.

    Production hands us ``Decimal`` straight off the ORM column, but the
    legacy Telegram tuple shape is ``float`` and some call sites still
    build it that way. ``sum`` raises on a mixed batch, so everything
    becomes ``Decimal`` here — via ``repr`` for floats, which is how
    :mod:`backend.bot.formatters.money` avoids binary-float artefacts
    like ``45000.000000000007``.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value.strip())
    return Decimal(repr(value))
