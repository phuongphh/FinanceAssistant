"""Phase 3.9.5 Epic 5 custom emoji rendering tests."""

import backend.bot.utils.emoji_animation as emoji_animation
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


def test_render_context_filters_by_touchpoint(monkeypatch):
    # Inject a test mapping with valid IDs so this exercises the filtering
    # logic regardless of whether the production YAML currently has real
    # custom_emoji_ids (placeholders are disabled until a Premium account
    # harvests real IDs — see content/emoji_animation_map.yaml).
    fake_map = {
        "check_mark": {
            "static": "✅",
            "animation_id": "check-id",
            "contexts": ["transaction"],
        },
        "money_bag": {
            "static": "💰",
            "animation_id": "money-id",
            "contexts": ["transaction"],
        },
        "warning": {
            "static": "⚠️",
            "animation_id": "warning-id",
            "contexts": ["briefing"],
        },
    }
    monkeypatch.setattr(emoji_animation, "load_emoji_animation_map", lambda: fake_map)

    text, entities = render_context("✅ Ghi xong 💰", "transaction")

    assert text == "✅ Ghi xong 💰"
    assert [entity["type"] for entity in entities] == ["custom_emoji", "custom_emoji"]


def test_render_context_returns_empty_when_animation_ids_missing(monkeypatch):
    """Current production state: placeholder IDs disabled → no entities emitted.

    Verifies the code path stays wired but Telegram simply renders the static
    unicode emoji (which is also the non-Premium client fallback), so callers
    can keep using ``render_context`` even before real IDs are harvested.
    """
    placeholder_map = {
        "money_bag": {"static": "💰", "contexts": ["briefing"]},
        "check_mark": {"static": "✅", "contexts": ["transaction"]},
    }
    monkeypatch.setattr(emoji_animation, "load_emoji_animation_map", lambda: placeholder_map)

    text, entities = render_context("✅ Ghi xong 💰", "transaction")

    assert text == "✅ Ghi xong 💰"
    assert entities == []
