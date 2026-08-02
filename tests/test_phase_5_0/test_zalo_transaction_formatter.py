"""Phase 5.0 #2.4 — the Zalo-native transaction formatter.

:mod:`backend.bot.handlers.transaction` covers the routing decision; this
module covers what the chosen text actually says. The two constraints the
channel imposes — ~300 display characters, ≤ 2 emoji, no Markdown — are
asserted here rather than left to the notifier's blind truncation, because
truncation would cut a batch mid-item and drop the trailing hint.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.adapters.zalo_notifier import ZALO_MESSAGE_MAX_CHARS, strip_markdown
from backend.bot.formatters.zalo_transaction import (
    MAX_BATCH_ITEMS,
    MAX_BATCH_MERCHANT_CHARS,
    MAX_MERCHANT_CHARS,
    format_zalo_transaction,
    format_zalo_transaction_batch,
)

YESTERDAY = date.today() - timedelta(days=1)

# Zalo shows the marker literally, so no output may contain one. Parens are
# excluded from this list on purpose: they appear in ordinary Vietnamese
# copy and only mean something to a Markdown parser next to a "[...]" span,
# which the handler already unwraps.
MARKDOWN_MARKERS = ("*", "_", "~", "[", "]", "`", "<", ">")


def _emoji_count(text: str) -> int:
    return sum(1 for char in text if ord(char) > 0x2000 and char not in "·—–…")


def _assert_channel_safe(text: str) -> None:
    assert len(text) <= ZALO_MESSAGE_MAX_CHARS, f"{len(text)} chars: {text!r}"
    assert not any(marker in text for marker in MARKDOWN_MARKERS), text
    # The notifier would strip Markdown anyway; asserting the formatter is
    # already clean means the length above is the length the user sees.
    assert strip_markdown(text) == text
    assert _emoji_count(text) <= 2, text


# --------------------------------------------------------------------------
# Single transaction
# --------------------------------------------------------------------------


def test_expense_states_what_was_recorded_and_nothing_else():
    text = format_zalo_transaction(
        merchant="Phở Bát Đàn", amount=Decimal("45000"), category_code="food"
    )

    assert text == "✅ Đã ghi Phở Bát Đàn 45,000đ · Ăn uống"
    _assert_channel_safe(text)


def test_amount_is_written_in_full_not_rounded():
    """This is the receipt for something the user just typed. "45k" invites
    a second guess about what was actually stored."""
    text = format_zalo_transaction(
        merchant="Cà phê", amount=Decimal("2350000"), category_code="food"
    )

    assert "2,350,000đ" in text


def test_money_in_uses_the_receiving_verb():
    text = format_zalo_transaction(
        merchant="Lương tháng 8",
        amount=Decimal("25000000"),
        category_code="salary",
        transaction_type="money_in",
    )

    assert text.startswith("✅ Đã nhận")
    _assert_channel_safe(text)


def test_unknown_category_falls_back_instead_of_raising():
    text = format_zalo_transaction(
        merchant="Gì đó", amount=Decimal("1000"), category_code="not_a_category"
    )

    assert "Gì đó 1,000đ" in text
    _assert_channel_safe(text)


def test_missing_merchant_gets_a_neutral_label():
    """An OCR row with no merchant must still read as a sentence, not as
    "Đã ghi  45,000đ" with a hole in it."""
    text = format_zalo_transaction(
        merchant=None, amount=Decimal("45000"), category_code="food"
    )

    assert "Giao dịch 45,000đ" in text


def test_newline_in_a_merchant_name_cannot_break_the_line_structure():
    """Merchant names are free text the user typed and there is no escaping
    on a plain-text channel — a pasted multi-line name would otherwise turn
    one row into three."""
    text = format_zalo_transaction(
        merchant="Quán\nBún\n  Chả", amount=Decimal("45000"), category_code="food"
    )

    assert "Quán Bún Chả" in text
    assert text.count("\n") == 0


def test_today_needs_no_date_row_but_a_backdated_day_does():
    today = format_zalo_transaction(
        merchant="A",
        amount=Decimal("1000"),
        category_code="food",
        expense_date=date.today(),
    )
    backdated = format_zalo_transaction(
        merchant="A",
        amount=Decimal("1000"),
        category_code="food",
        expense_date=YESTERDAY,
    )

    assert "Ngày giao dịch" not in today
    assert YESTERDAY.strftime("%d/%m/%Y") in backdated


def test_optional_rows_appear_in_a_stable_order():
    """Date, then source, then hint. The order is what makes the message
    scannable; a swap would read as noise before facts."""
    text = format_zalo_transaction(
        merchant="Phở",
        amount=Decimal("45000"),
        category_code="food",
        expense_date=YESTERDAY,
        source_label="Techcombank",
        show_edit_hint=True,
    )

    assert text.splitlines() == [
        "✅ Đã ghi Phở 45,000đ · Ăn uống",
        f"Ngày giao dịch: {YESTERDAY.strftime('%d/%m/%Y')}",
        "Từ: Techcombank",
        "Muốn sửa hay xoá thì mở Bé Tiền trên Telegram nhé.",
    ]
    _assert_channel_safe(text)


# --------------------------------------------------------------------------
# Batch
# --------------------------------------------------------------------------


def test_empty_batch_renders_nothing_to_send():
    assert format_zalo_transaction_batch(items=[]) == ""


def test_batch_shows_every_item_and_a_full_total():
    text = format_zalo_transaction_batch(
        items=[
            ("Phở", Decimal("45000"), "food"),
            ("Cà phê", Decimal("35000"), "food"),
        ]
    )

    assert text.splitlines() == [
        "✅ Đã ghi 2 khoản · tổng 80,000đ",
        "- Phở 45k",
        "- Cà phê 35k",
    ]
    _assert_channel_safe(text)


def test_a_long_batch_is_capped_so_the_hint_survives():
    """The adapter's truncation is blind: it would cut the list mid-item
    and take the hint with it. Capping here keeps the last line intact."""
    items = [(f"Quán {i}", Decimal("50000"), "food") for i in range(12)]

    text = format_zalo_transaction_batch(items=items, show_edit_hint=True)

    lines = text.splitlines()
    assert sum(1 for line in lines if line.startswith("- Quán")) == MAX_BATCH_ITEMS
    assert f"- và {12 - MAX_BATCH_ITEMS} khoản nữa" in lines
    assert lines[-1].endswith("Telegram nhé.")
    # The total counts all twelve, not just the rows shown.
    assert "12 khoản · tổng 600,000đ" in lines[0]
    _assert_channel_safe(text)


def test_a_batch_at_the_cap_gets_no_and_n_more_line():
    items = [(f"Q{i}", Decimal("1000"), "food") for i in range(MAX_BATCH_ITEMS)]

    text = format_zalo_transaction_batch(items=items)

    assert "khoản nữa" not in text


def test_worst_case_batch_still_fits_the_bubble():
    """Cap + long merchant names + every optional row. If this fits, the
    ceiling holds for anything the sender can produce."""
    items = [("Nhà hàng Hải sản Biển Đông chi nhánh 3", Decimal("1250000"), "food")] * 9

    text = format_zalo_transaction_batch(
        items=items,
        expense_date=YESTERDAY,
        source_label="Techcombank Visa Signature",
        show_edit_hint=True,
    )

    _assert_channel_safe(text)


def test_wide_rows_are_dropped_before_the_parts_that_matter():
    """The row count is a ceiling, not a promise. When each row is wide,
    fewer are listed — the header, the total and the trailing rows are
    what the user is checking, so they are never what gets cut."""
    items = [("Nhà hàng Hải sản Biển Đông chi nhánh 3", Decimal("1250000"), "food")] * 9

    text = format_zalo_transaction_batch(
        items=items,
        expense_date=YESTERDAY,
        source_label="Techcombank Visa Signature",
        show_edit_hint=True,
    )

    lines = text.splitlines()
    shown = sum(1 for line in lines if line.startswith("- Nhà hàng"))
    assert 0 < shown < MAX_BATCH_ITEMS
    assert "9 khoản · tổng 11,250,000đ" in lines[0]
    assert f"- và {9 - shown} khoản nữa" in lines
    assert lines[-3] == f"Ngày giao dịch: {YESTERDAY.strftime('%d/%m/%Y')}"
    assert lines[-2] == "Từ: Techcombank Visa Signature"
    assert lines[-1] == "Muốn sửa hay xoá thì mở Bé Tiền trên Telegram nhé."


@pytest.mark.parametrize("count", [2, 3, 6, 12, 40])
@pytest.mark.parametrize("width", [1, 12, 30, 80, 200])
def test_the_and_n_more_count_always_matches_the_rows_shown(count, width):
    """The arithmetic has to hold at every width, because the width is
    what decides how many rows survive. An off-by-one here tells the user
    a transaction was recorded that isn't in the list, or hides one."""
    items = [("M" * width, Decimal("1250000"), "food") for _ in range(count)]

    text = format_zalo_transaction_batch(
        items=items,
        expense_date=YESTERDAY,
        source_label="Techcombank Visa Signature",
        show_edit_hint=True,
    )

    lines = text.splitlines()
    shown = sum(1 for line in lines if line.startswith("- M"))
    hidden = count - shown
    if hidden:
        assert f"- và {hidden} khoản nữa" in lines
    else:
        assert "khoản nữa" not in text
    assert f"{count} khoản" in lines[0]
    _assert_channel_safe(text)


def test_a_batch_row_clips_its_merchant_on_a_word_boundary():
    """Cutting mid-word reads as corruption; backing off to the last
    space reads as an abbreviation."""
    text = format_zalo_transaction_batch(
        items=[
            ("Nhà hàng Hải sản Biển Đông chi nhánh 3", Decimal("1250000"), "food"),
            ("Phở", Decimal("45000"), "food"),
        ]
    )

    row = next(line for line in text.splitlines() if line.startswith("- Nhà"))
    assert row == "- Nhà hàng Hải sản Biển… 1tr250"
    # Short names are left exactly as the user wrote them.
    assert "- Phở 45k" in text


def test_a_merchant_with_no_spaces_is_still_bounded():
    """A pasted token — an order id, a bank descriptor — has no word
    boundary to back off to, so the clip has to cut it anyway."""
    text = format_zalo_transaction_batch(items=[("M" * 200, Decimal("1000"), "food")])

    row = next(line for line in text.splitlines() if line.startswith("- M"))
    assert row.count("M") <= MAX_BATCH_MERCHANT_CHARS
    assert row.endswith("1k")
    assert "…" in row


def test_a_single_transaction_gets_a_wider_but_still_bounded_name():
    """One transaction has the bubble to itself, so it keeps more of the
    name than a batch row does — but not so much that the hint below it
    gets pushed out."""
    long_name = "Công ty Cổ phần Thương mại Dịch vụ Xuất nhập khẩu Toàn Cầu Việt Nam"

    text = format_zalo_transaction(
        merchant=long_name,
        amount=Decimal("1250000"),
        category_code="food",
        expense_date=YESTERDAY,
        source_label="Techcombank Visa Signature",
        show_edit_hint=True,
    )

    header = text.splitlines()[0]
    assert len(header) > MAX_BATCH_MERCHANT_CHARS  # wider than a batch row
    assert long_name not in header  # but not unbounded
    assert header.startswith("✅ Đã ghi Công ty Cổ phần")
    assert text.splitlines()[-1].endswith("Telegram nhé.")
    _assert_channel_safe(text)


def test_a_merchant_at_the_bound_is_left_alone():
    """Clipping something that already fits would put an ellipsis on a
    name the user typed in full."""
    name = "A" * MAX_MERCHANT_CHARS

    text = format_zalo_transaction(
        merchant=name, amount=Decimal("1000"), category_code="food"
    )

    assert name in text
    assert "…" not in text


@pytest.mark.parametrize(
    "amounts",
    [
        [Decimal("45000"), 35000, "20000"],
        [45000.0, Decimal("35000")],
        [Decimal("45000"), Decimal("35000")],
    ],
    ids=["decimal_int_str", "float_and_decimal", "all_decimal"],
)
def test_mixed_amount_types_sum_without_a_type_error(amounts):
    """Production hands us ``Decimal`` off the ORM, but the legacy Telegram
    tuple shape is ``float`` and some call sites still build it that way.
    A bare ``sum`` raises on the mix."""
    items = [(f"Q{i}", amount, "food") for i, amount in enumerate(amounts)]

    text = format_zalo_transaction_batch(items=items)

    assert str(int(sum(Decimal(str(a)) for a in amounts))) in text.replace(",", "")


def test_float_amounts_do_not_leak_binary_artefacts():
    """``Decimal(45000.1)`` is 45000.099999…; going through ``repr`` is
    what keeps the total readable."""
    text = format_zalo_transaction_batch(
        items=[("A", 45000.1, "food"), ("B", 0.9, "food")]
    )

    assert "45,001đ" in text
    assert "0000000" not in text


def test_batch_newlines_are_flattened_per_row():
    text = format_zalo_transaction_batch(
        items=[("Quán\nA", Decimal("1000"), "food"), ("B", Decimal("2000"), "food")]
    )

    assert len(text.splitlines()) == 3
    assert "- Quán A 1k" in text
