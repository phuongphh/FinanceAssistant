from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.twin import label_resolver
from backend.twin.services import life_outcome_translator
from backend.twin.services.growth_rate_calculator import GrowthRateSnapshot
from backend.twin.services.twin_narrative_service import _clean_output
from backend.twin.views.present_anchor import build_present_anchor_view
from infra.cache.life_outcome_cache import bucket_amount


def test_label_resolver_defaults_to_weather_vocabulary():
    labels = label_resolver.labels_for_payload()

    assert labels["p10"]["label"] == "🌧️ Khiêm tốn"
    assert labels["p50"]["label"] == "⛅ Bình thường"
    assert labels["p90"]["label"] == "☀️ Lạc quan"


def test_label_resolver_can_show_technical_terms():
    labels = label_resolver.labels_for_payload(show_technical_terms=True)

    assert labels["p10"]["label"] == "P10"
    assert labels["p50"]["label"] == "P50"
    assert labels["p90"]["label"] == "P90"


def test_narrative_clean_output_replaces_technical_terms_with_plain_fallback():
    text = "Nếu giữ nhịp hiện tại, P50 năm 10 có thể đạt 316.7 tỷ. Mình theo dõi cùng bạn nhé."

    cleaned = _clean_output(text, "316.7 tỷ", 10)

    assert "P50" not in cleaned
    assert "vùng bình thường" in cleaned


def test_present_anchor_formats_delta_and_growth_rate():
    view = build_present_anchor_view(
        GrowthRateSnapshot(
            current_net_worth=Decimal("850000000"),
            weekly_delta=Decimal("12000000"),
            monthly_growth_rate=Decimal("50000000"),
            days_observed=90,
            has_enough_data=True,
        ),
        target_year=2030,
        target_p50=Decimal("5200000000"),
        breakdown={"cash": Decimal("300000000"), "stock": Decimal("550000000")},
    )

    assert view.present_label == "Hiện tại: 850tr"
    assert view.weekly_delta_label == "↑ Tăng 12tr"
    assert view.growth_rate_label == "Tốc độ ~ 50tr/tháng"
    assert (
        view.projected_if_maintained_label
        == "Nếu duy trì, năm 2030 có thể đạt ⛅ 5.2 tỷ"
    )


def test_present_anchor_handles_small_delta_and_new_user():
    view = build_present_anchor_view(
        GrowthRateSnapshot(
            current_net_worth=Decimal("10000000"),
            weekly_delta=Decimal("1000"),
            monthly_growth_rate=None,
            days_observed=3,
            has_enough_data=False,
        )
    )

    assert view.weekly_delta_label == "Ổn định"
    assert view.growth_rate_label == "Đang theo dõi nhịp"


def test_life_outcome_bucket_and_sanitize_guardrails():
    assert bucket_amount(Decimal("149000000")) == Decimal("200000000")
    assert life_outcome_translator.sanitize_phrase("Bạn nên mua cổ phiếu X") == ""
    phrase = life_outcome_translator.sanitize_phrase("quỹ dự phòng vững hơn")
    assert phrase.startswith("có thể")
    assert len(phrase.split()) <= 30


@pytest.mark.asyncio
async def test_life_outcome_uses_fallback_without_db():
    phrase = await life_outcome_translator.translate(
        None,
        amount_vnd=Decimal("5200000000"),
        target_year=2030,
        user_context={"location": "TP.HCM"},
    )

    assert "có thể" in phrase
    assert len(phrase.split()) <= 30
