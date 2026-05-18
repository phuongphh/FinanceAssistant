from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.twin.services.action_suggestion_service import ActionSuggestion, render_action_card
from backend.twin.services.causality_service import CausalityBreakdown, build_weighted_factors
from backend.twin.services.negative_delta_service import build_negative_delta_message, validate_respectful_copy
from backend.twin.services.return_tease_service import next_briefing_time
from backend.twin.services.threshold_service import is_noticeable
from infra.event_bus.twin_events import TwinEvent, should_trigger_recompute


def test_twin_event_filter_matches_epic_sources():
    user_id = uuid4()

    assert should_trigger_recompute(TwinEvent("asset.created", user_id)) is True
    assert should_trigger_recompute(TwinEvent("asset.updated", user_id)) is True
    assert should_trigger_recompute(TwinEvent("income.added", user_id)) is True
    assert should_trigger_recompute(TwinEvent("goal.milestone_reached", user_id)) is True
    assert should_trigger_recompute(TwinEvent("expense.added", user_id, amount_vnd=Decimal("199000"))) is False
    assert should_trigger_recompute(TwinEvent("expense.added", user_id, amount_vnd=Decimal("200000"))) is True


def test_threshold_inclusive_and_segment_adjusted():
    assert is_noticeable("starter", Decimal("0.1"), Decimal("1000000")) is True
    assert is_noticeable("mass_affluent", Decimal("0.5"), Decimal("9000000")) is False
    assert is_noticeable("mass_affluent", Decimal("1.0"), Decimal("1")) is True
    assert is_noticeable("hnw", Decimal("0.5"), Decimal("1")) is True
    assert is_noticeable("hnw", Decimal("0.1"), Decimal("50000000")) is True


def test_causality_weights_top_factors_and_other_bucket():
    factors = build_weighted_factors(
        [
            {"label": "Anh thêm 5tr tiết kiệm", "delta_absolute_vnd": 5_000_000, "factor_type": "asset"},
            {"label": "HPG tăng", "delta_absolute_vnd": 2_000_000, "factor_type": "market"},
            {"label": "Lãi suất tăng", "delta_absolute_vnd": 1_000_000, "factor_type": "rate"},
            {"label": "Khác 1", "delta_absolute_vnd": 1_000_000, "factor_type": "other"},
            {"label": "Khác 2", "delta_absolute_vnd": 1_000_000, "factor_type": "other"},
            {"label": "Khác 3", "delta_absolute_vnd": 1_000_000, "factor_type": "other"},
        ],
        max_items=3,
    )

    assert [f.factor for f in factors][:3] == [
        "Anh thêm 5tr tiết kiệm",
        "HPG tăng",
        "Lãi suất tăng",
    ]
    assert factors[-1].factor == "Khác"
    assert sum(f.contribution_pct for f in factors) == Decimal("100.0")


def test_negative_delta_copy_is_respectful_and_actionable():
    breakdown = CausalityBreakdown(
        direction="negative",
        delta_pct=Decimal("-1.2"),
        delta_absolute_vnd=Decimal("-12000000"),
        factors=(build_weighted_factors([{"label": "chi tiêu vượt nhịp", "delta_absolute_vnd": 12_000_000}])[0],),
        text="",
        forward_sentence=None,
        show_breakdown=True,
    )
    suggestion = ActionSuggestion(
        type="negative_review",
        title="Review 3 khoản chi lớn nhất tháng",
        description="Mở lại 3 khoản chi lớn để kiểm tra khoản nào cần điều chỉnh nhẹ.",
        time_estimate_minutes=5,
        deep_link="betien://expense/review-top3",
        buttons=(),
    )

    message = build_negative_delta_message(breakdown, suggestion)

    assert message.visual_cue == "🌧️ Twin Mưa Cuối Tuần"
    assert message.should_notify is True
    assert validate_respectful_copy(message.text) is True
    assert "Review 3 khoản chi" in message.text


def test_action_card_keeps_five_minute_constraint():
    suggestion = ActionSuggestion(
        type="goal_progress",
        title="Cập nhật tiến độ mục tiêu",
        description="Thêm một mốc tiến độ nhỏ.",
        time_estimate_minutes=5,
        deep_link="betien://goals/progress",
        buttons=(),
    )

    assert "Khoảng 5 phút" in render_action_card(suggestion)


def test_return_tease_schedules_next_briefing_softly():
    now = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    send_at = next_briefing_time(now)

    assert send_at > now
    assert send_at.hour == 1  # 08:00 ICT
