from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.twin.flows.first_time_view import build_story_flow, should_show_full_story
from backend.twin.views.scenario_card import mascot_for, scenario_cards_for_point


def test_mascot_variants_are_mapped_to_weather_scenarios():
    p10 = mascot_for("p10")
    p50 = mascot_for("p50")
    p90 = mascot_for("p90")

    assert p10.emoji == "🌧️"
    assert "áo mưa" in p10.outfit
    assert p50.emoji == "⛅"
    assert "dù" in p50.outfit
    assert p90.emoji == "☀️"
    assert "kính" in p90.outfit
    assert p10.display_url.endswith("betien_2030_p10_v1.png")


def test_scenario_cards_include_mascot_fallback_payload():
    cards = scenario_cards_for_point(
        {"year": 10, "p10": "100", "p50": "200", "p90": "300"},
        {"p10": {"label": "🌧️ Khiêm tốn"}},
    )

    assert len(cards) == 3
    assert cards[0]["label"] == "🌧️ Khiêm tốn"
    assert cards[0]["mascot"]["fallback"] == "🌧️"
    assert cards[1]["mascot"]["asset_url"]


def test_story_flow_full_has_five_screens_and_compact_has_two():
    data = {
        "present_anchor": {"present_label": "Hiện tại: 850tr"},
        "scenario_cards": [],
        "life_outcome": "có thể quỹ dự phòng vững hơn",
    }

    full = build_story_flow(data, full_flow=True)
    compact = build_story_flow(data, full_flow=False)

    assert full["mode"] == "full"
    assert [s["id"] for s in full["screens"]] == [
        "present",
        "scenarios",
        "why",
        "action",
        "detail",
    ]
    assert compact["mode"] == "compact"
    assert [s["id"] for s in compact["screens"]] == ["scenarios", "detail"]


@pytest.mark.asyncio
async def test_should_show_full_story_respects_30_day_window():
    user_id = uuid4()

    class FakeResult:
        def __init__(self, item):
            self.item = item

        def scalar_one_or_none(self):
            return self.item

    class FakeDb:
        def __init__(self, item):
            self.item = item

        async def execute(self, _stmt):
            return FakeResult(self.item)

    assert await should_show_full_story(FakeDb(None), user_id) is True
    recent = SimpleNamespace(created_at=datetime.now(timezone.utc) - timedelta(days=2))
    old = SimpleNamespace(created_at=datetime.now(timezone.utc) - timedelta(days=31))
    assert await should_show_full_story(FakeDb(recent), user_id) is False
    assert await should_show_full_story(FakeDb(old), user_id) is True
