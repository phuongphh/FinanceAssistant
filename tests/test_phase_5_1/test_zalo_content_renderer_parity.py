"""Phase 5.1 #2.2/#2.3 — the three surfaces Zalo could not carry in 5.0.

What is worth pinning is not that the methods return a string. It is the
four decisions that make the strings *different* from Telegram's:

1. **The caption is composed, not truncated.** Telegram's Twin caption
   carries a narrative, a present anchor and three scenario cards. None of
   that fits, and cutting it at character 300 would end mid-clause on
   whichever field happened to be long that day. So the Zalo caption is
   built from bounded inputs only — the pronoun, the year, three money
   figures — and the unbounded fields are never read. The tests below feed
   pathological values into every excluded field and assert the output does
   not move.
2. **Lines are dropped whole, from the tail.** The copy is written as
   separate lines in priority order precisely so that fitting can be a
   choice of *which* line to lose rather than where to cut one.
3. **A missing chart downgrades, it does not raise.** On Telegram the chart
   is the message; here the numbers are already spelled out above it.
4. **Buttons come back empty.** A Zalo message carries an image or buttons,
   not both, and the Twin carries the image. E4 #4.1 owns re-enabling them.

Every test injects a fake chart renderer. That is not only for speed: it is
the proof that the renderer is pure — no matplotlib, no DB, no env — which
is what lets it stay in ``adapters/`` without a flag.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

import pytest

from backend.adapters.zalo_content_renderer import ZaloContentRenderer
from backend.ports.content_renderer import (
    MilestoneSnapshot,
    TwinComparisonSnapshot,
    TwinViewSnapshot,
)
from backend.utils.zalo_limits import ZALO_MESSAGE_MAX_CHARS

_SALUTATIONS = ("anh", "chị", "bạn")

# A cone only has to be truthy — the renderer never looks inside it, it
# hands it to the injected chart renderer.
_CONE = [{"year": 2045, "p50": 1}]

# ``zalo_copy.text()`` returns the *raw template* when a format key is
# missing, so an unsubstituted brace is the signature of a copy/renderer
# mismatch reaching the user. Nothing in content/zalo.yaml uses a literal
# brace, which is what makes this a safe global assertion.
_BRACE_RE = re.compile(r"[{}]")

_MARKDOWN_CHARS = ("*", "_", "`", "[", "]", "~")


@pytest.fixture()
def chart_calls() -> list[tuple]:
    return []


@pytest.fixture()
def renderer(chart_calls) -> ZaloContentRenderer:
    def fake_chart(cone, optimal=None, **kwargs):
        chart_calls.append((cone, optimal))
        return b"PNG-BYTES"

    return ZaloContentRenderer(chart_renderer=fake_chart)


@pytest.fixture()
def failing_renderer() -> ZaloContentRenderer:
    def boom(cone, optimal=None, **kwargs):
        raise RuntimeError("matplotlib exploded")

    return ZaloContentRenderer(chart_renderer=boom)


def _twin(**overrides) -> TwinViewSnapshot:
    kwargs = dict(
        user_name="Phương",
        target_year=2045,
        p10=Decimal("1000000000"),
        p50=Decimal("2000000000"),
        p90=Decimal("3000000000"),
        age_text="45 tuổi",
        cone=_CONE,
    )
    kwargs.update(overrides)
    return TwinViewSnapshot(**kwargs)


def _comparison(**overrides) -> TwinComparisonSnapshot:
    kwargs = dict(
        target_year=2045,
        current_p50=Decimal("2000000000"),
        optimal_p50=Decimal("3000000000"),
        delta_pct="+42%",
        actions="Tăng tiết kiệm 2tr/tháng",
        disclaimer="Đây là dự phóng tham khảo.",
        current_cone=_CONE,
        optimal_cone=_CONE,
    )
    kwargs.update(overrides)
    return TwinComparisonSnapshot(**kwargs)


def _rendered(renderer, snapshot):
    """Dispatch a snapshot to its method, so shared checks can be generic."""
    if isinstance(snapshot, TwinViewSnapshot):
        return renderer.render_twin_view(snapshot)
    if isinstance(snapshot, TwinComparisonSnapshot):
        return renderer.render_twin_comparison(snapshot)
    return renderer.render_milestone(snapshot)


# ---------------------------------------------------------------------------
# The channel rules, on rendered output rather than on the copy file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("salutation", _SALUTATIONS)
@pytest.mark.parametrize("kind", ["twin", "comparison", "milestone"])
def test_every_surface_renders_for_every_salutation(renderer, salutation, kind):
    # tests/test_phase_5_1/test_zalo_copy.py proves the *strings* render for
    # all three. This proves the renderer actually threads the pronoun into
    # them — a copy file full of {salutation} and a renderer that forgets to
    # pass it would pass that suite and ship a literal brace.
    snapshot = {
        "twin": lambda: _twin(salutation=salutation),
        "comparison": lambda: _comparison(salutation=salutation),
        "milestone": lambda: MilestoneSnapshot(
            text="", title="Quỹ khẩn cấp 6 tháng", salutation=salutation
        ),
    }[kind]()

    content = _rendered(renderer, snapshot)

    assert content.text
    assert not _BRACE_RE.search(content.text), content.text
    assert len(content.text) <= ZALO_MESSAGE_MAX_CHARS
    found = [ch for ch in _MARKDOWN_CHARS if ch in content.text]
    assert not found, f"{found} would be shown raw by Zalo"


@pytest.mark.parametrize("salutation", _SALUTATIONS)
def test_the_pronoun_the_caller_chose_is_the_pronoun_that_arrives(
    renderer, salutation
):
    text = renderer.render_twin_view(_twin(salutation=salutation)).text

    assert salutation in text
    # And no other pronoun leaked in from a hardcoded default.
    for other in set(_SALUTATIONS) - {salutation}:
        assert f" {other} " not in f" {text} "


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_missing_salutation_falls_back_to_ban_rather_than_a_hole(renderer, blank):
    # ``salutation_of`` already guarantees one of the three, but the port
    # field is a plain str with a default and nothing stops a future caller
    # from passing None through. The bubble must still read as a sentence.
    text = renderer.render_twin_view(_twin(salutation=blank)).text

    assert "bạn" in text
    assert not _BRACE_RE.search(text)


# ---------------------------------------------------------------------------
# Twin view
# ---------------------------------------------------------------------------


def test_the_twin_caption_names_the_year_and_all_three_figures(renderer):
    text = renderer.render_twin_view(_twin()).text

    assert "2045" in text
    # format_money_short on 1/2/3 tỷ — the point is that all three bounds
    # are present, not the exact spelling, which money.py owns.
    assert text.count("tỷ") >= 3


def test_the_stale_note_appears_only_when_the_data_is_stale(renderer):
    fresh = renderer.render_twin_view(_twin(is_stale=False)).text
    stale = renderer.render_twin_view(_twin(is_stale=True)).text

    assert "cập nhật tài sản" in stale
    assert "cập nhật tài sản" not in fresh
    # The stale line is *additive* — it warns, it does not replace.
    assert len(stale) > len(fresh)


def test_the_disclaimer_survives_even_with_the_stale_line_present(renderer):
    # It is the last line, so it is the first thing tail-dropping would
    # lose. If this ever fails, the copy grew past the bubble and the fix
    # is shorter copy, not a bigger limit.
    text = renderer.render_twin_view(_twin(is_stale=True)).text

    assert "không phải lời hứa" in text


def test_the_unbounded_telegram_fields_are_never_read(renderer):
    # The whole reason the caption is composed rather than truncated. If a
    # future edit starts interpolating any of these, the output moves and
    # this fails — which is the intended alarm.
    baseline = renderer.render_twin_view(_twin()).text

    noisy = renderer.render_twin_view(
        _twin(
            user_name="X" * 400,
            narrative="N" * 400,
            present_anchor="P" * 400,
            life_outcome="L" * 400,
            age_text="A" * 400,
            scenario_labels={"k": "S" * 400},
            scenario_cards=[{"label": "C" * 400}],
        )
    ).text

    assert noisy == baseline


# ---------------------------------------------------------------------------
# Twin comparison
# ---------------------------------------------------------------------------


def test_the_comparison_leads_with_the_gap(renderer):
    text = renderer.render_twin_comparison(_comparison()).text

    assert "2045" in text
    assert "+42%" in text


def test_only_the_first_suggested_action_survives(renderer):
    # Telegram shows three, ordered by impact. Three inside a 300-character
    # bubble crowds out the number the list is about, and the ordering is
    # what makes dropping the tail safe.
    text = renderer.render_twin_comparison(
        _comparison(
            actions="Tăng tiết kiệm 2tr/tháng\nGiảm chi ăn ngoài\nMở sổ tiết kiệm"
        )
    ).text

    assert "Tăng tiết kiệm 2tr/tháng" in text
    assert "Giảm chi ăn ngoài" not in text
    assert "Mở sổ tiết kiệm" not in text


def test_blank_leading_lines_in_actions_do_not_produce_an_empty_suggestion(renderer):
    text = renderer.render_twin_comparison(
        _comparison(actions="\n\n   \nTăng tiết kiệm 2tr/tháng")
    ).text

    assert "Tăng tiết kiệm 2tr/tháng" in text


def test_no_actions_at_all_drops_the_line_rather_than_leaving_a_stub(renderer):
    text = renderer.render_twin_comparison(_comparison(actions="")).text

    assert "Việc nên làm" not in text
    assert "\n\n" not in text  # no gap where the line used to be


def test_an_enormous_action_is_clipped_before_it_eats_the_bubble(renderer):
    text = renderer.render_twin_comparison(_comparison(actions="Z" * 500)).text

    assert len(text) <= ZALO_MESSAGE_MAX_CHARS
    # The headline is the first line and must not be the casualty of a
    # caller handing us a runaway string.
    assert "2045" in text


def test_the_telegram_disclaimer_field_is_not_the_one_that_ships(renderer):
    # ``disclaimer`` is Telegram's, written for Telegram's length. Zalo's
    # closing line comes from content/zalo.yaml like every other string.
    text = renderer.render_twin_comparison(
        _comparison(disclaimer="D" * 400)
    ).text

    assert "D" * 20 not in text
    assert len(text) <= ZALO_MESSAGE_MAX_CHARS


# ---------------------------------------------------------------------------
# Milestone
# ---------------------------------------------------------------------------


def test_a_structured_milestone_says_what_changed_in_the_twin(renderer):
    content = renderer.render_milestone(
        MilestoneSnapshot(
            text="ignored when title is present",
            title="Quỹ khẩn cấp 6 tháng",
            effect="Twin lạc quan hơn 4%",
            salutation="anh",
        )
    )

    assert "Quỹ khẩn cấp 6 tháng" in content.text
    assert "Twin lạc quan hơn 4%" in content.text
    assert "ignored" not in content.text


def test_a_milestone_without_an_effect_still_celebrates(renderer):
    content = renderer.render_milestone(
        MilestoneSnapshot(text="", title="Quỹ khẩn cấp 6 tháng")
    )

    assert "Quỹ khẩn cấp 6 tháng" in content.text
    assert "Twin đổi theo" not in content.text


def test_without_a_title_the_pre_composed_body_is_the_fallback(renderer):
    # Not the good path — it yields whatever the calling surface wrote for a
    # bigger screen — but a milestone that renders imperfectly beats one
    # that raises on a caller which has not been taught the new fields.
    content = renderer.render_milestone(MilestoneSnapshot(text="Chúc mừng anh!"))

    assert content.text == "Chúc mừng anh!"


def test_a_runaway_title_is_clipped_not_allowed_to_swallow_the_bubble(renderer):
    content = renderer.render_milestone(MilestoneSnapshot(text="", title="T" * 500))

    assert len(content.text) <= ZALO_MESSAGE_MAX_CHARS
    # The closing line is what makes it a celebration rather than a log
    # entry, so the clip must happen inside the title, not by dropping it.
    assert "mình đi tiếp nhé" in content.text


def test_markup_in_a_caller_supplied_value_is_stripped(renderer):
    content = renderer.render_milestone(
        MilestoneSnapshot(text="", title="**Quỹ khẩn cấp**", effect="`+4%`")
    )

    assert "*" not in content.text
    assert "`" not in content.text
    assert "Quỹ khẩn cấp" in content.text


def test_a_multiline_title_becomes_one_line(renderer):
    # A newline inside a value would silently create a copy line the
    # priority ordering knows nothing about.
    content = renderer.render_milestone(
        MilestoneSnapshot(text="", title="Quỹ\nkhẩn\ncấp")
    )

    assert "Quỹ khẩn cấp" in content.text


# ---------------------------------------------------------------------------
# The chart
# ---------------------------------------------------------------------------


def test_the_twin_ships_the_chart_bytes_and_names_the_file(renderer, chart_calls):
    content = renderer.render_twin_view(_twin())

    assert content.images == (b"PNG-BYTES",)
    assert content.filename == "be-tien-twin.png"
    assert chart_calls == [(_CONE, None)]


def test_the_comparison_passes_both_cones_to_the_chart(renderer, chart_calls):
    content = renderer.render_twin_comparison(_comparison())

    assert content.images == (b"PNG-BYTES",)
    assert content.filename == "be-tien-twin-optimal.png"
    assert chart_calls == [(_CONE, _CONE)]


def test_an_empty_cone_skips_the_chart_rather_than_calling_it(renderer, chart_calls):
    content = renderer.render_twin_view(_twin(cone=[]))

    assert content.images == ()
    assert content.filename is None
    assert chart_calls == []


def test_a_failing_chart_downgrades_to_text_instead_of_raising(failing_renderer):
    # The Zalo-specific call. On Telegram the chart *is* the message and a
    # failure should be loud; here the numbers are already spelled out in
    # the text above it, so a user who gets the bubble without the picture
    # has still been answered.
    content = failing_renderer.render_twin_view(_twin())

    assert content.images == ()
    assert content.filename is None
    assert "2045" in content.text


def test_the_downgrade_is_logged_so_it_is_not_invisible(failing_renderer, caplog):
    with caplog.at_level(
        logging.WARNING, logger="backend.adapters.zalo_content_renderer"
    ):
        failing_renderer.render_twin_comparison(_comparison())

    assert "zalo.twin.chart_failed" in caplog.text


def test_the_renderer_never_turns_bytes_into_a_url_itself(renderer):
    # Publishing is #2.4's job in the notifier. A renderer that knew about
    # the media service would be a renderer that needs a database session,
    # and this class is constructed without one.
    content = renderer.render_twin_view(_twin())

    assert all(isinstance(blob, bytes) for blob in content.images)
    assert "http" not in content.text


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["twin", "comparison", "milestone"])
def test_no_surface_emits_buttons_yet(renderer, kind):
    # A Zalo message carries an image or buttons, not both, and the Twin
    # carries the image. E4 #4.1 owns re-enabling them once the dispatcher
    # can route the text an oa.query.show tap produces.
    snapshot = {
        "twin": _twin,
        "comparison": _comparison,
        "milestone": lambda: MilestoneSnapshot(text="", title="Mốc"),
    }[kind]()

    assert _rendered(renderer, snapshot).buttons == ()
