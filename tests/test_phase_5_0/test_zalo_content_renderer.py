"""The Zalo side of the ContentRenderer port (Phase 5.0 #4.2).

Three claims are worth pinning here, and they are what the sections below
are organised around:

1. **Only briefings render.** Twin, comparison and milestone raise, loudly,
   because on Zalo they would arrive as a caption for an invisible chart or
   as a proactive send the 48h window cannot carry. A stub that returned
   empty content would look like a Twin with nothing in it.
2. **What arrives is plain.** No Markdown markers, no HTML, no bracketed
   pseudo-buttons — Zalo renders none of it, so the user would read the
   markup itself.
3. **What arrives fits.** The bubble cuts at ~300 characters. The renderer
   drops whole lines, then whole sentences, before it ever cuts a word,
   because a briefing's last line is its recommendation and a blind cut
   keeps the preamble and loses the point.
"""

from __future__ import annotations

import logging

import pytest

from backend.adapters.zalo_content_renderer import (
    ZaloContentRenderer,
    fit_briefing_text,
)
from backend.ports.content_renderer import BriefingSnapshot, Button, MilestoneSnapshot
from backend.utils.zalo_limits import ZALO_MESSAGE_MAX_CHARS


@pytest.fixture()
def renderer() -> ZaloContentRenderer:
    return ZaloContentRenderer()


# ---------------------------------------------------------------------------
# What Phase 5.0 deliberately does not render
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method",
    ["render_twin_view", "render_twin_comparison", "render_milestone"],
)
def test_the_surfaces_zalo_cannot_carry_refuse_rather_than_degrade(renderer, method):
    # Passing None is safe precisely because the guard is unconditional:
    # nothing touches the snapshot before the raise.
    with pytest.raises(NotImplementedError) as exc:
        getattr(renderer, method)(None)

    # The message names where the work went, so the next person doesn't
    # have to guess whether this is a gap or a decision.
    assert "5.1" in str(exc.value)


def test_briefings_are_the_one_surface_that_does_render(renderer):
    content = renderer.render_briefing(BriefingSnapshot(text="Tháng này bạn chi 3tr."))

    assert content.text == "Tháng này bạn chi 3tr."


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


def test_buttons_are_dropped_and_not_spelled_out(renderer):
    # Every briefing button points at a Telegram screen. Rendering the
    # label as text would name a destination the reader cannot reach.
    snapshot = BriefingSnapshot(
        text="Tháng này bạn chi 3tr.",
        buttons=((Button("Xem chi tiết", callback_data="menu:report"),),),
    )

    content = renderer.render_briefing(snapshot)

    assert content.buttons == ()
    assert "Xem chi tiết" not in content.text


def test_a_bracketed_pseudo_button_loses_its_brackets_not_its_label(renderer):
    # ``strip_markdown`` unwraps ``[label](url)`` but leaves a bare span
    # alone — on Zalo that survives as brackets around text, which reads
    # as a tappable thing that isn't.
    content = renderer.render_briefing(
        BriefingSnapshot(text="Số dư đang mỏng. [Xem chi tiết] để biết thêm.")
    )

    assert content.text == "Số dư đang mỏng. Xem chi tiết để biết thêm."


def test_a_real_markdown_link_keeps_the_label_and_drops_the_url(renderer):
    content = renderer.render_briefing(
        BriefingSnapshot(text="Đọc [hướng dẫn](https://example.com/x) nhé.")
    )

    assert content.text == "Đọc hướng dẫn nhé."
    assert "http" not in content.text


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("**Cảnh báo** số dư", "Cảnh báo số dư"),
        ("__Cảnh báo__ số dư", "Cảnh báo số dư"),
        ("*Cảnh báo* số dư", "Cảnh báo số dư"),
        ("~~Cảnh báo~~ số dư", "Cảnh báo số dư"),
        ("`45,000đ` đã ghi", "45,000đ đã ghi"),
        ("<b>Cảnh báo</b> số dư", "Cảnh báo số dư"),
        (r"Số dư 3\.5tr", "Số dư 3.5tr"),
    ],
)
def test_markup_never_reaches_the_bubble(renderer, raw, expected):
    assert renderer.render_briefing(BriefingSnapshot(text=raw)).text == expected


def test_the_hole_a_stripped_heading_leaves_is_closed_up(renderer):
    # "**Tháng 8**" on its own line becomes an empty line once the markers
    # go. Three blank lines in a 300-character bubble read as broken.
    raw = "Tổng kết\n\n\n\n\nChi 3tr, thu 5tr."

    assert renderer.render_briefing(BriefingSnapshot(text=raw)).text == (
        "Tổng kết\n\nChi 3tr, thu 5tr."
    )


def test_paragraph_breaks_survive(renderer):
    # Collapsing runs must not flatten the structure the copy relies on:
    # one blank line is a paragraph, not noise.
    raw = "Tổng kết tháng 8.\n\nChi 3tr, thu 5tr."

    assert renderer.render_briefing(BriefingSnapshot(text=raw)).text == raw


def test_empty_text_stays_empty_rather_than_raising(renderer):
    # The notifier already refuses to send an empty body; the renderer's
    # job is to not turn "nothing to say" into a crash on the send path.
    assert renderer.render_briefing(BriefingSnapshot(text="")).text == ""


# ---------------------------------------------------------------------------
# Fitting the bubble
# ---------------------------------------------------------------------------


def test_a_briefing_that_already_fits_is_untouched():
    text = "Tháng 8 bạn chi 3tr trên ngân sách 5tr.\n\nGiữ nhịp này là ổn."

    assert fit_briefing_text(text) == text


def test_a_long_briefing_loses_whole_lines_not_half_a_word():
    lines = [f"Dòng {i} " + "x" * 60 for i in range(10)]

    fitted = fit_briefing_text("\n".join(lines))

    assert len(fitted) <= ZALO_MESSAGE_MAX_CHARS
    # Every surviving line is a line that was written, start to finish.
    assert all(line in lines for line in fitted.split("\n"))
    assert "…" not in fitted


def test_the_leading_lines_are_the_ones_that_survive():
    # Briefings are written most-important-first, so the tail is the
    # cheapest thing to lose.
    lines = [f"Dòng {i} " + "x" * 60 for i in range(10)]

    fitted = fit_briefing_text("\n".join(lines))

    assert fitted.startswith(lines[0])
    assert lines[-1] not in fitted


def test_an_over_budget_first_line_is_cut_between_sentences():
    sentences = [f"Câu số {i} nói về một khoản chi nào đó." for i in range(12)]

    fitted = fit_briefing_text(" ".join(sentences))

    assert len(fitted) <= ZALO_MESSAGE_MAX_CHARS
    assert fitted.endswith(".")
    assert "…" not in fitted
    assert fitted.startswith(sentences[0])


def test_one_unbroken_sentence_falls_back_to_a_word_cut():
    text = " ".join(["từ"] * 200)

    fitted = fit_briefing_text(text)

    assert len(fitted) <= ZALO_MESSAGE_MAX_CHARS
    # The ellipsis is the honest part: the reader can see it was clipped.
    assert fitted.endswith("…")
    # And the cut landed between words, not inside one.
    assert not fitted.rstrip("…").endswith("t")


def test_a_single_enormous_word_is_still_bounded():
    # No boundary of any kind to back off to — the budget still holds.
    fitted = fit_briefing_text("x" * 900)

    assert len(fitted) <= ZALO_MESSAGE_MAX_CHARS
    assert fitted.endswith("…")


def test_the_word_cut_is_the_last_resort_and_says_so(caplog):
    with caplog.at_level(
        logging.DEBUG, logger="backend.adapters.zalo_content_renderer"
    ):
        fit_briefing_text(" ".join(["từ"] * 200))

    assert "zalo.briefing.word_clipped" in caplog.text


def test_a_leading_blank_line_does_not_short_circuit_the_search():
    # An empty first part fits trivially. If that counted as "something
    # fits", the result would be an empty bubble.
    text = "\n" + "\n".join(f"Dòng {i} " + "x" * 60 for i in range(10))

    fitted = fit_briefing_text(text)

    assert fitted
    assert len(fitted) <= ZALO_MESSAGE_MAX_CHARS


def test_the_budget_is_measured_after_markup_is_stripped():
    # 250 characters of text wrapped in 200 characters of bold markers is
    # a message that fits — unless the budget is checked too early.
    text = " ".join(f"**từ{i}**" for i in range(30))

    fitted = fit_briefing_text(text)

    assert "*" not in fitted
    assert "…" not in fitted
    assert fitted == " ".join(f"từ{i}" for i in range(30))


def test_the_limit_is_a_parameter_so_callers_with_less_room_can_say_so():
    # The image-caption path on Zalo is capped at 100, not 300.
    fitted = fit_briefing_text("Tháng 8 bạn chi 3tr. " * 20, limit=100)

    assert len(fitted) <= 100


def test_the_result_never_carries_leading_or_trailing_whitespace():
    fitted = fit_briefing_text("   \n\n  Tháng 8 bạn chi 3tr.  \n\n  ")

    assert fitted == "Tháng 8 bạn chi 3tr."


# ---------------------------------------------------------------------------
# The port contract
# ---------------------------------------------------------------------------


def test_the_renderer_returns_the_shape_the_port_promises(renderer):
    content = renderer.render_briefing(BriefingSnapshot(text="Xin chào."))

    assert isinstance(content.text, str)
    assert content.images == ()
    assert content.buttons == ()
    assert content.filename is None


def test_milestone_refuses_even_with_a_perfectly_renderable_body(renderer):
    # Milestone bodies are plain text too — the refusal is about the
    # channel being reactive-first, not about the payload being hard.
    with pytest.raises(NotImplementedError):
        renderer.render_milestone(MilestoneSnapshot(text="Chúc mừng!"))
