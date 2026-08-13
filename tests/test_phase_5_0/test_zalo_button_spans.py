"""``unwrap_button_spans`` — the one implementation of the button rule.

Telegram copy marks an inline button as ``[Xem chi tiết]``. Zalo OA has no
inline keyboard in 5.0, so a surviving span is a control the reader will
try to tap and nothing will happen.

Two callers share this helper — the inbound handler flattening a dispatch
outcome, and the content renderer fitting a briefing — and they layer their
own whitespace policy on top. What is pinned here is the part they must
*not* diverge on: which shapes get unwrapped, and that the pass runs after
:func:`strip_markdown` rather than before.
"""

from __future__ import annotations

import pytest

from backend.adapters.zalo_notifier import strip_markdown, unwrap_button_spans


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[Xem báo cáo]", "Xem báo cáo"),
        ("Số dư mỏng. [Xem chi tiết] nhé.", "Số dư mỏng. Xem chi tiết nhé."),
        ("[A] [B]", "A B"),
        ("không có nút", "không có nút"),
        ("", ""),
    ],
)
def test_a_span_loses_its_brackets_and_keeps_its_label(raw, expected):
    # Unwrap, never delete: "[Xem báo cáo]" is often the only verb in the
    # sentence, so dropping the span outright leaves a dangling line.
    assert unwrap_button_spans(raw) == expected


def test_a_span_running_across_lines_is_left_alone():
    # An unclosed bracket on one line and a stray one on the next is prose
    # with brackets in it, not markup. Rewriting it would corrupt the text.
    raw = "Ghi chú [chưa\nđóng] ở đây"

    assert unwrap_button_spans(raw) == raw


def test_nested_brackets_unwrap_all_the_way_down():
    # A single pass matches the inner span and leaves the outer pair
    # orphaned as "[A]" — still a bracket in front of the reader, which
    # is the one outcome this function exists to prevent. So it repeats
    # to a fixed point.
    assert unwrap_button_spans("[[A]]") == "A"


def test_stripping_first_is_what_keeps_a_url_out_of_the_bubble():
    # The ordering contract, stated as the failure it prevents.
    raw = "xem tại [đây](https://x.vn)"

    assert unwrap_button_spans(strip_markdown(raw)) == "xem tại đây"


def test_unwrapping_first_would_strand_the_url():
    # The wrong order, asserted so the reason for the right one is not
    # folk knowledge: unwrapping destroys the "[label](url)" shape that
    # strip_markdown matches on, and the URL then survives.
    raw = "xem tại [đây](https://x.vn)"

    assert "https://x.vn" in strip_markdown(unwrap_button_spans(raw))


@pytest.mark.parametrize("raw", ["Chọn [A] hoặc [B]", "[[A]]", "[chưa\nđóng]"])
def test_the_helper_is_idempotent(raw):
    # Both callers sit upstream of a notifier that sanitises again. A
    # second pass has to be a no-op or the shared path is not composable —
    # including on the nested case, which is why the unwrap repeats.
    once = unwrap_button_spans(raw)

    assert unwrap_button_spans(once) == once


def test_the_two_callers_agree_on_which_spans_get_unwrapped():
    # The point of the shared helper: the same input cannot come out of
    # the handler bracketed and out of the renderer plain. Only the
    # whitespace policy is allowed to differ.
    from backend.adapters.zalo_content_renderer import fit_briefing_text
    from backend.bot.handlers.zalo_inbound import _plain_body

    raw = "Tổng tài sản 1 tỷ 200.\n[Xem chi tiết]"

    for rendered in (_plain_body(raw), fit_briefing_text(raw)):
        assert "[" not in rendered and "]" not in rendered
        assert "Xem chi tiết" in rendered
