"""Phase 4.1 Epic A — focused tests on pure-function services.

Database-touching paths are covered by integration tests once dev
fixtures are wired up; this module exercises the deterministic logic
that's safe to run without a Postgres connection:

  - A.1 wealth segment inference + amount parsing
  - A.3 cost estimation
  - A.5 Sentry PII scrub
  - A.7 feedback triage copy
  - A.8 first-briefing decorator
"""

from __future__ import annotations

from decimal import Decimal


# ----- A.1: wealth inference --------------------------------------------


def test_segment_starter_under_100tr():
    from backend.services.onboarding.wealth_inference_service import infer_segment

    assert infer_segment(Decimal("50_000_000")) == "starter"
    assert infer_segment(Decimal("99_999_999")) == "starter"
    assert infer_segment(0) == "starter"


def test_segment_young_pro_100_500tr():
    from backend.services.onboarding.wealth_inference_service import infer_segment

    assert infer_segment(Decimal("100_000_000")) == "young_pro"
    assert infer_segment(Decimal("499_999_999")) == "young_pro"


def test_segment_mass_affluent_500tr_5ty():
    from backend.services.onboarding.wealth_inference_service import infer_segment

    assert infer_segment(Decimal("500_000_000")) == "mass_affluent"
    assert infer_segment(Decimal("4_999_999_999")) == "mass_affluent"


def test_segment_hnw_over_5ty():
    from backend.services.onboarding.wealth_inference_service import infer_segment

    assert infer_segment(Decimal("5_000_000_000")) == "hnw"
    assert infer_segment(Decimal("100_000_000_000")) == "hnw"


# ----- A.1: amount parser -----------------------------------------------


def test_parse_amount_shortcuts():
    from backend.services.onboarding.onboarding_service import parse_asset_amount

    assert parse_asset_amount("200tr") == Decimal("200_000_000")
    assert parse_asset_amount("200 tr") == Decimal("200_000_000")
    assert parse_asset_amount("1.5 tỷ") == Decimal("1_500_000_000")
    assert parse_asset_amount("1,5 tỷ") == Decimal("1_500_000_000")
    assert parse_asset_amount("500k") == Decimal("500_000")
    assert parse_asset_amount("5 tỉ") == Decimal("5_000_000_000")
    assert parse_asset_amount("100 triệu") == Decimal("100_000_000")


def test_parse_amount_raw_numbers():
    from backend.services.onboarding.onboarding_service import parse_asset_amount

    assert parse_asset_amount("200000000") == Decimal("200_000_000")
    assert parse_asset_amount("200,000,000") == Decimal("200_000_000")
    assert parse_asset_amount("200.000.000") == Decimal("200_000_000")


def test_parse_amount_invalid():
    from backend.services.onboarding.onboarding_service import parse_asset_amount

    assert parse_asset_amount("abc") is None
    assert parse_asset_amount("") is None
    assert parse_asset_amount("   ") is None


# ----- A.3: cost estimation ---------------------------------------------


def test_deepseek_cost_under_free_cap():
    """500 classify calls × 200 tokens ~= 100K tokens must cost < 30k VND
    (free tier cap). This is the design budget for v1.
    """
    from backend.services.cost.budget_service import estimate_call_cost_vnd

    cost = estimate_call_cost_vnd("deepseek", tokens_in=50_000, tokens_out=50_000)
    assert cost < Decimal("30_000"), f"500-call day busts free cap: {cost}"


def test_claude_ocr_per_page():
    from backend.services.cost.budget_service import estimate_call_cost_vnd

    cost = estimate_call_cost_vnd("claude", page_count=1)
    assert cost > 0
    # 100-page receipt blast must still be flagged before busting cap.
    big = estimate_call_cost_vnd("claude", page_count=100)
    assert big > cost * 50


def test_whisper_per_second():
    from backend.services.cost.budget_service import estimate_call_cost_vnd

    cost = estimate_call_cost_vnd("whisper", audio_seconds=60.0)
    assert cost > 0


def test_unknown_provider_zero_cost():
    from backend.services.cost.budget_service import estimate_call_cost_vnd

    # Unknown providers must not accidentally bill the user.
    assert estimate_call_cost_vnd("foo") == Decimal("0")


# ----- A.5: Sentry PII scrub --------------------------------------------


def test_sentry_scrub_money():
    from backend.adapters.observability.sentry_adapter import _scrub_string

    assert "[redacted_n]" in _scrub_string("user has 200000000 VND")
    # Short numbers stay (e.g. HTTP status codes).
    assert "[redacted_n]" not in _scrub_string("status 403")


def test_sentry_scrub_email():
    from backend.adapters.observability.sentry_adapter import _scrub_string

    assert "[email]" in _scrub_string("contact me at foo@bar.com please")


def test_sentry_scrub_vn_phone():
    from backend.adapters.observability.sentry_adapter import _scrub_string

    assert "[phone]" in _scrub_string("call +84901234567")
    assert "[phone]" in _scrub_string("call 0901234567 now")


def test_sentry_before_send_hashes_user_id():
    from backend.adapters.observability.sentry_adapter import before_send

    event = {
        "user": {
            "id": "a1b2c3d4-5678-9abc-def0-123456789012",
            "email": "leak@example.com",
        },
        "extra": {},
    }
    out = before_send(event)
    assert "id" not in out["user"]
    assert out["user"]["email"] == "[email]"
    assert "user_id_hash" in out["user"]
    assert len(out["user"]["user_id_hash"]) == 12


# ----- A.7: feedback triage copy ----------------------------------------


def test_triage_templates_have_all_keys():
    from backend.feedback.services.feedback_triage_service import (
        available_templates,
        get_template,
    )

    expected = {
        "thanks_logged",
        "clarify_request",
        "feature_acknowledged",
        "bug_apology",
        "not_supported_yet",
    }
    got = set(available_templates())
    assert got == expected, f"missing templates: {expected - got}"
    for key in expected:
        body = get_template(key)
        assert body and "Bé Tiền" in body, f"template {key} missing brand voice"


# ----- A.8: first-briefing decorator ------------------------------------


def test_first_briefing_decorate_wraps_with_explainer_and_button():
    from backend.services.briefing import first_briefing_service

    original = "Test briefing payload."
    decorated, markup = first_briefing_service.decorate(original)

    assert "briefing đầu tiên" in decorated
    assert original in decorated  # don't drop the underlying briefing
    assert markup["inline_keyboard"][0][0]["callback_data"].startswith(
        "first_briefing:"
    )


def test_first_briefing_explanation_text_is_non_empty():
    from backend.services.briefing import first_briefing_service

    text = first_briefing_service.explanation_text()
    assert len(text) > 50
    assert "Bé Tiền" in text


# ----- A.4: cost report rendering ---------------------------------------


def test_cost_report_renders_with_zero_data():
    from datetime import date

    from backend.services.cost.cost_report_service import CostReport

    rpt = CostReport(report_date=date(2026, 5, 12))
    rendered = rpt.to_telegram_section()
    assert "Cost" in rendered
    assert "2026-05-12" in rendered
    # No burst flag when there's no data.
    assert "🚨" not in rendered


def test_cost_report_burst_flag():
    from datetime import date
    from decimal import Decimal as D

    from backend.services.cost.cost_report_service import CostReport

    rpt = CostReport(
        report_date=date(2026, 5, 12),
        total_vnd_by_provider={"deepseek": D("100000")},
        total_vnd=D("100000"),
        seven_day_avg_vnd=D("20000"),
        is_burst=True,
    )
    rendered = rpt.to_telegram_section()
    assert rendered.startswith("🚨")


# ----- Founding member discount API -------------------------------------


def test_founding_discount_is_50pct():
    from types import SimpleNamespace
    from decimal import Decimal as D

    from backend.services.founding.founding_member_service import compute_discount

    founding = SimpleNamespace(is_founding_member=True)
    non = SimpleNamespace(is_founding_member=False)
    assert compute_discount(founding) == D("0.5")
    assert compute_discount(non) == D("0")
