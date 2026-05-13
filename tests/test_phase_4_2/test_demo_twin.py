"""Demo Twin onboarding regression tests.

Covers the fix for "clicking 'Để Bé Tiền dùng demo trước' shows the wrong
narrative + never renders the Twin chart":

  - Demo narrative / caption / ack are wired and distinct from the real ones.
  - ``compute_demo_cone`` is deterministic, cached, and falls back to a
    hard-coded cone when Monte Carlo raises so the first product moment
    can never crash.
  - ``compute_failed`` copy is honest (no phantom 1-minute promise) and
    ships with a retry button.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml


def _load_first_twin_intro() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[2]
        / "content"
        / "onboarding"
        / "first_twin_intro.yaml"
    )
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --- YAML copy -----------------------------------------------------------


def test_demo_narrative_does_not_claim_ownership():
    """Demo narrative must NOT say 'Twin của bạn' — that broke trust."""
    copy = _load_first_twin_intro()
    demo_text = copy["demo_narrative"].lower()
    assert "demo" in demo_text
    assert "giả định" in demo_text
    assert "twin của bạn" not in demo_text


def test_real_narrative_still_personal():
    copy = _load_first_twin_intro()
    real = copy["narrative"].lower()
    assert "twin tài chính" in real
    assert "của bạn" in real


def test_demo_caption_marks_demo_and_excludes_name():
    copy = _load_first_twin_intro()
    rendered = copy["demo_caption"].format(horizon=10)
    assert "Twin demo" in rendered
    assert "50 triệu" in rendered
    # Demo caption must NOT inject {name} — no real user owns this Twin.
    assert "{name}" not in copy["demo_caption"]


def test_demo_ack_does_not_imply_we_recorded_user_cash():
    copy = _load_first_twin_intro()
    ack = copy["demo_ack"]
    # The old "✅ Bé Tiền ghi nhận: 50tr" wording made users think we
    # banked their money. Demo ack must clarify 'giả định'.
    assert "giả định" in ack
    assert "ghi nhận" not in ack


def test_compute_failed_copy_does_not_promise_phantom_retry():
    copy = _load_first_twin_intro()
    failed = copy["compute_failed"]
    # The old copy said 'mất khoảng 1 phút ... sẽ nhắn ngay khi xong' but
    # no background job actually exists. That phrasing is BANNED.
    assert "1 phút" not in failed
    assert "thử lại" in failed.lower()
    assert copy["compute_failed_retry_label"]
    assert copy["compute_failed_retry_callback"] == "onboarding_v2:retry_twin"


# --- twin_narrative_service_v2 helpers -----------------------------------


def test_narrative_text_branches_on_demo_flag():
    from backend.twin.services import twin_narrative_service_v2 as svc

    real = svc.narrative_text(demo=False)
    demo = svc.narrative_text(demo=True)
    assert real != demo
    assert "demo" in demo.lower()


def test_chart_caption_branches_on_demo_flag():
    from backend.twin.services import twin_narrative_service_v2 as svc

    real = svc.chart_caption(name="Phương", horizon_years=10, demo=False)
    demo = svc.chart_caption(name="Phương", horizon_years=10, demo=True)
    assert "Phương" in real
    assert "Phương" not in demo
    assert "demo" in demo.lower()


def test_compute_failed_keyboard_has_retry_callback():
    from backend.twin.services import twin_narrative_service_v2 as svc

    kb = svc.compute_failed_keyboard()
    rows = kb["inline_keyboard"]
    assert len(rows) == 1 and len(rows[0]) == 1
    button = rows[0][0]
    assert button["callback_data"] == "onboarding_v2:retry_twin"
    assert "thử lại" in button["text"].lower()


# --- demo_twin_service ---------------------------------------------------


def test_compute_demo_cone_is_cached_and_deterministic():
    from backend.twin.services import demo_twin_service

    demo_twin_service.reset_cache_for_tests()
    first = demo_twin_service.compute_demo_cone()
    second = demo_twin_service.compute_demo_cone()
    # Identity equality — second call returned the cached list, no recompute.
    assert first is second
    assert len(first) == demo_twin_service.DEMO_HORIZON_YEARS + 1
    assert first[0]["year"] == 0
    assert first[-1]["year"] == demo_twin_service.DEMO_HORIZON_YEARS


def test_compute_demo_cone_falls_back_when_monte_carlo_raises():
    """Belt-and-suspenders: if numpy regresses or the engine raises for any
    reason, the demo cone path MUST still return the hard-coded fallback —
    we never let the first product moment crash."""
    from backend.twin.services import demo_twin_service

    demo_twin_service.reset_cache_for_tests()

    def _boom(*args: Any, **kwargs: Any):
        raise RuntimeError("monte-carlo offline")

    with patch.object(demo_twin_service, "simulate_portfolio", _boom):
        cone = demo_twin_service.compute_demo_cone()

    assert cone == demo_twin_service._FALLBACK_CONE
    # Cache was poisoned with the fallback; reset so other tests get the
    # real Monte Carlo cone again.
    demo_twin_service.reset_cache_for_tests()


def test_demo_cone_renders_to_png_via_chart_adapter():
    from backend.adapters.chart_renderer import render_cone_chart
    from backend.twin.services import demo_twin_service

    demo_twin_service.reset_cache_for_tests()
    cone = demo_twin_service.compute_demo_cone()
    png = render_cone_chart(cone)
    assert png.startswith(b"\x89PNG"), "demo cone did not render as a PNG"
    assert len(png) > 1000, "demo PNG suspiciously small — likely empty chart"
