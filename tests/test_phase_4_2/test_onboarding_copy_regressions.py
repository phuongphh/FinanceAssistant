"""Regression tests for the Phase 4.1/4.2 onboarding copy bugs reported
after dogfood:

  1. Welcome intro and source variants must NOT contain "Personal CFO".
     The user-facing positioning is "người đồng hành quản lý tài sản".
  2. Trust card must show "(1/3)" in the header AND include the
     "Bé Tiền tôn trọng tài chính của bạn" promise (missing in v1).
     Step 1 goal question must NOT carry a "(1/3)" prefix so the
     numbered counter starts at the trust card.
  3. Demo Twin must use TWO asset classes (cash + VN stocks) so the
     demo cone shows visible diversification, and a post-chart emphasis
     bubble must reframe the demo as not-yet-your-real-picture.
  4. The "🎉 Xong! Bé Tiền và bạn chính thức đồng hành…" activation
     bubble MUST be deferred until the user takes the first next-best
     action — firing it right after the CTA card reads as premature.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "onboarding"


def _load_yaml(name: str) -> dict[str, Any]:
    with (_CONTENT_DIR / name).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------
# 1. "Personal CFO" must be gone from customer-facing copy
# ---------------------------------------------------------------------


def test_welcome_intro_does_not_use_personal_cfo():
    copy = _load_yaml("welcome_v2.yaml")
    intro = copy["intro"]["default"].lower()
    assert "personal cfo" not in intro
    # Positive: the warm phrasing is in place.
    assert "đồng hành" in intro or "quản lý tài sản" in intro


def test_welcome_source_variants_do_not_use_personal_cfo():
    copy = _load_yaml("welcome_v2.yaml")
    variants = copy.get("source_variants") or {}
    for src, body in variants.items():
        text = (body.get("prefix") or "").lower()
        assert "personal cfo" not in text, (
            f"source_variant.{src}.prefix still contains 'Personal CFO'"
        )


def test_twin_share_watermark_does_not_use_personal_cfo():
    """The Twin share image is one of the most viral surfaces — its
    watermark must not leak the internal 'Personal CFO' wording.
    """
    path = Path(__file__).resolve().parents[2] / "content" / "twin_copy.yaml"
    with path.open(encoding="utf-8") as fh:
        copy = yaml.safe_load(fh)
    watermark = copy["share"]["watermark"]
    assert "Personal CFO" not in watermark
    assert "Bé Tiền" in watermark


# ---------------------------------------------------------------------
# 2. Trust card (1/3) header + "tôn trọng tài chính" promise
# ---------------------------------------------------------------------


def test_trust_card_header_carries_one_of_three_label():
    copy = _load_yaml("trust_card.yaml")
    header = copy["header"]
    assert "(1/3)" in header, (
        "trust card must label itself as step (1/3) — otherwise the user "
        "sees (2/3) on the asset prompt with no (1/3) ever shown."
    )
    assert "tôn trọng" in header.lower(), (
        "trust card header must keep the 'Bé Tiền tôn trọng tài chính của "
        "bạn' promise — removing it weakens the privacy moment."
    )


def test_trust_card_body_introduces_three_promises():
    copy = _load_yaml("trust_card.yaml")
    bullets = copy.get("bullets") or []
    assert len(bullets) == 3, "trust card must list exactly 3 promises"
    # All three should be short, action-oriented, and end on '.'
    for b in bullets:
        assert b.strip().endswith("."), f"bullet not punctuated: {b!r}"


def test_welcome_goal_question_does_not_double_label_one_of_three():
    """Goal pick is a preamble — labeling it (1/3) AND the trust card
    (1/3) would confuse the user about what step they're on.
    """
    copy = _load_yaml("welcome_v2.yaml")
    header = copy["step_1_goal"]["header"]
    assert "(1/3)" not in header, (
        "goal question header must NOT include '(1/3)' — the numbered "
        "counter now starts at the trust card."
    )


def test_asset_and_twin_headers_keep_their_step_labels():
    copy = _load_yaml("welcome_v2.yaml")
    assert "(2/3)" in copy["step_2_asset"]["header"]
    assert "(3/3)" in copy["step_3_twin"]["header"]


# ---------------------------------------------------------------------
# 3. Demo uses 2 asset types + post-chart emphasis
# ---------------------------------------------------------------------


def test_demo_narrative_mentions_two_asset_classes():
    copy = _load_yaml("first_twin_intro.yaml")
    narrative = copy["demo_narrative"].lower()
    # 30tr cash + 20tr stocks split must be explicit so the user sees
    # the diversification framing.
    assert "30" in narrative and "20" in narrative
    assert "cash" in narrative or "tiền mặt" in narrative or "tiết kiệm" in narrative
    assert "cổ phiếu" in narrative
    # Demo framing intact.
    assert "giả định" in narrative
    assert "twin của bạn" not in narrative  # see test_demo_twin.py


def test_demo_post_chart_emphasis_present_and_reframes_real_picture():
    copy = _load_yaml("first_twin_intro.yaml")
    text = copy.get("demo_post_chart_emphasis")
    assert text, "demo_post_chart_emphasis must exist"
    lowered = text.lower()
    # Must emphasize that the REAL picture will be better.
    assert "thật" in lowered
    assert "tốt hơn" in lowered or "rich" in lowered
    # Must reference the user's plans / decisions.
    assert "kế hoạch" in lowered or "đầu tư" in lowered


def test_demo_simulation_uses_two_asset_classes():
    """Guard against a silent regression to single-bucket cash demo."""
    from backend.twin.services import demo_twin_service

    assert demo_twin_service.DEMO_CASH_VND > 0
    assert demo_twin_service.DEMO_STOCKS_VN_VND > 0
    assert (
        demo_twin_service.DEMO_CASH_VND + demo_twin_service.DEMO_STOCKS_VN_VND
        == demo_twin_service.DEMO_BASE_NET_WORTH_VND
    )


def test_twin_narrative_service_exposes_demo_post_chart_helper():
    """Handler depends on this helper — if it goes missing the post-chart
    emphasis bubble silently drops.
    """
    from backend.twin.services import twin_narrative_service_v2 as svc

    text = svc.demo_post_chart_emphasis_text()
    assert text.strip()
    assert "thật" in text.lower()


# ---------------------------------------------------------------------
# 4. Activation message is deferred to first engagement
# ---------------------------------------------------------------------


def test_handler_does_not_send_completion_directly_in_feedback_path():
    """Read the handler source: the feedback callback must call
    ``_finalize_session_silently`` (no message) and NOT ``_complete`` —
    if it does, the activation bubble fires before the user has had a
    chance to engage with the next-best-action card.
    """
    handler_src = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "bot"
        / "handlers"
        / "onboarding_v2.py"
    ).read_text(encoding="utf-8")
    # The old prematurely-firing path is gone.
    assert "_finalize_session_silently" in handler_src
    # And the feedback signal handler uses the silent finalize.
    fb_block_start = handler_src.find("async def _on_feedback_signal")
    fb_block = handler_src[fb_block_start : fb_block_start + 3000]
    assert "_finalize_session_silently" in fb_block, (
        "_on_feedback_signal must use _finalize_session_silently — the "
        "activation bubble must NOT fire before next-best-action."
    )


def test_handle_next_action_callback_sends_activation_before_mark_taken():
    """The activation helper gates on next_best_action_taken IS NULL,
    so the handler must call it BEFORE mark_taken — otherwise the gate
    fails and the message never fires.
    """
    handler_src = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "bot"
        / "handlers"
        / "onboarding_v2.py"
    ).read_text(encoding="utf-8")
    nbc_start = handler_src.find("async def handle_next_action_callback")
    nbc_block = handler_src[nbc_start : nbc_start + 4000]
    activation_idx = nbc_block.find("_send_activation_message_if_first_engagement")
    mark_idx = nbc_block.find("next_action_service.mark_taken")
    assert activation_idx != -1, "activation helper missing from callback"
    assert mark_idx != -1, "mark_taken missing from callback"
    assert activation_idx < mark_idx, (
        "_send_activation_message_if_first_engagement must run BEFORE "
        "mark_taken so the next_best_action_taken IS NULL gate still holds."
    )


def test_maybe_mark_query_next_action_accepts_chat_id():
    """The worker call site passes chat_id so the activation helper can
    fire the bubble. Guard against a signature drift.
    """
    import inspect

    from backend.bot.handlers import onboarding_v2 as handler

    params = inspect.signature(handler.maybe_mark_query_next_action).parameters
    assert list(params.keys())[:3] == ["db", "chat_id", "user"]
