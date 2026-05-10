"""Phase 3.9.5 Epic 5 custom emoji rendering tests."""

from backend.bot.utils.emoji_animation import render_context, render_with_animation


MAPPING = {
    "money_bag": {
        "static": "💰",
        "animation_id": "money-id",
        "contexts": ["briefing"],
    },
    "warning": {
        "static": "⚠️",
        "animation_id": "warning-id",
        "contexts": ["briefing"],
    },
}


def test_render_with_animation_all_mapped():
    text, entities = render_with_animation("💰 Tổng tài sản ⚠️", MAPPING)

    assert text == "💰 Tổng tài sản ⚠️"
    assert entities == [
        {
            "type": "custom_emoji",
            "offset": 0,
            "length": 2,
            "custom_emoji_id": "money-id",
        },
        {
            "type": "custom_emoji",
            "offset": 16,
            "length": 2,
            "custom_emoji_id": "warning-id",
        },
    ]


def test_render_with_animation_partial_mapping_keeps_static_emoji():
    text, entities = render_with_animation("💰 tăng 📈", MAPPING)

    assert text == "💰 tăng 📈"
    assert len(entities) == 1
    assert entities[0]["custom_emoji_id"] == "money-id"


def test_render_with_animation_none_mapped():
    text, entities = render_with_animation("Không có emoji mapped 📈", MAPPING)

    assert text == "Không có emoji mapped 📈"
    assert entities == []


def test_render_context_filters_by_touchpoint():
    text, entities = render_context("✅ Ghi xong 💰", "transaction")

    assert text == "✅ Ghi xong 💰"
    assert [entity["type"] for entity in entities] == ["custom_emoji", "custom_emoji"]
