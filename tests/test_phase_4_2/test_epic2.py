import uuid
from types import SimpleNamespace

import pytest

from backend.models.onboarding_session import (
    GOAL_PLAN_GOAL,
    GOAL_TRACK_SPENDING,
    GOAL_UNDERSTAND_WEALTH,
)
from backend.services.briefing import briefing_content_quality_service
from backend.services.onboarding import next_action_service


class _FakeDB:
    def __init__(self, goal):
        self.session = SimpleNamespace(goal_choice=goal)

    async def get(self, model, user_id):
        return self.session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,goal,button_key",
    [
        ("demo", GOAL_UNDERSTAND_WEALTH, "add_asset"),
        ("demo", GOAL_PLAN_GOAL, "add_asset"),
        ("demo", GOAL_TRACK_SPENDING, "add_asset"),
        ("real_no_income", GOAL_UNDERSTAND_WEALTH, "add_income"),
        ("real_no_income", GOAL_PLAN_GOAL, "add_income"),
        ("real_no_income", GOAL_TRACK_SPENDING, "log_expense"),
        ("real_with_income", GOAL_UNDERSTAND_WEALTH, "set_goal"),
        ("real_with_income", GOAL_PLAN_GOAL, "set_goal"),
        ("real_with_income", GOAL_TRACK_SPENDING, "log_expense"),
    ],
)
async def test_next_action_matrix_has_9_unique_ctas(
    monkeypatch, state, goal, button_key
):
    async def fake_asset_state(db, user_id):
        return state

    monkeypatch.setattr(next_action_service, "asset_state", fake_asset_state)
    cta = await next_action_service.compute(_FakeDB(goal), uuid.uuid4())

    assert cta.asset_state == state
    assert cta.goal == goal
    assert cta.button_key == button_key
    assert cta.text
    assert cta.message_text.startswith("💡 Bước tiếp theo dành cho bạn:")
    assert "hỏi Bé Tiền" in cta.message_text


def test_next_action_yaml_contains_unique_copy_for_each_cell():
    copy = next_action_service.load_copy()
    texts = [cell["text"] for row in copy["matrix"].values() for cell in row.values()]

    assert len(texts) == 9
    assert len(set(texts)) == 9


def test_briefing_quality_templates_have_editorial_hook_and_short_copy():
    copy = briefing_content_quality_service.load_templates()
    templates = list(copy["templates"].values()) + [copy["fallback"]]

    assert len(copy["templates"]) >= 5
    for item in templates:
        text = item["insight_text"]
        assert text.startswith("Bé Tiền nhận thấy")
        assert len(text) < 200
        assert item["suggested_query"]


def test_first_briefing_insight_render_text_is_plain_text_for_entities_send():
    from backend.services.briefing.briefing_content_quality_service import BriefingInsight

    insight = BriefingInsight(
        template_key="starter_first_asset",
        insight_text="Bé Tiền nhận thấy bạn đang ở bước xây nền.",
        suggested_query="bắt đầu quản lý tài chính",
    )

    assert "Hỏi thử: bắt đầu quản lý tài chính" in insight.render_text
    assert "<code>" not in insight.render_text
    assert "</code>" not in insight.render_text
