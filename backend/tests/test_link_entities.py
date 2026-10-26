"""Issue #1053 — briefing news links become Telegram ``text_link`` entities."""
from __future__ import annotations

from unittest.mock import patch

from backend.bot.utils.link_entities import (
    extract_link_entities,
    markdown_link,
    telegram_text_and_kwargs,
)


def _utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def test_markdown_link_round_trips_special_chars_without_visible_backslash():
    title = "VN-Index [phiên sáng] *tăng* 2% _HPG_ \\ dẫn dắt"
    url = "https://vnexpress.net/a_(b).html"
    link = markdown_link(title, url)

    plain, entities = extract_link_entities(f"• {link}")

    assert plain == f"• {title}"
    assert "\\[" not in plain
    assert entities == [
        {
            "type": "text_link",
            "offset": 2,
            "length": _utf16(title),
            "url": "https://vnexpress.net/a_(b%29.html",
        }
    ]


def test_extract_link_entities_uses_utf16_offsets_and_handles_many_links():
    text = "📰 Top tin:\n• [Giá vàng 🥇 tăng](https://cafef.vn/1)\n• [Tin hai](https://vnexpress.net/2)"
    plain, entities = extract_link_entities(text)

    assert plain == "📰 Top tin:\n• Giá vàng 🥇 tăng\n• Tin hai"
    first, second = entities
    assert first["url"] == "https://cafef.vn/1"
    assert first["offset"] == _utf16("📰 Top tin:\n• ")
    assert first["length"] == _utf16("Giá vàng 🥇 tăng")
    assert second["offset"] == _utf16("📰 Top tin:\n• Giá vàng 🥇 tăng\n• ")
    assert second["url"] == "https://vnexpress.net/2"


def test_non_http_or_missing_url_renders_plain_title():
    assert markdown_link("Tin", None) == "Tin"
    assert markdown_link("Tin", "javascript:alert(1)") == "Tin"


def test_text_without_links_is_unchanged():
    assert extract_link_entities("Không có link (ở đây)") == ("Không có link (ở đây)", [])


def test_telegram_kwargs_merge_link_and_emoji_entities_sorted():
    fake_map = {"sun": {"static": "🌤️", "animation_id": "sun-id", "contexts": ["briefing"]}}
    with patch("backend.bot.utils.emoji_animation.load_emoji_animation_map", return_value=fake_map):
        plain, kwargs = telegram_text_and_kwargs("• [Tin](https://cafef.vn/x)\n🌤️ Sáng", "briefing")

    assert plain == "• Tin\n🌤️ Sáng"
    assert [e["type"] for e in kwargs["entities"]] == ["text_link", "custom_emoji"]
    assert kwargs["entities"][1]["offset"] == _utf16("• Tin\n")


def test_telegram_kwargs_empty_when_nothing_to_annotate():
    with patch("backend.bot.utils.emoji_animation.load_emoji_animation_map", return_value={}):
        assert telegram_text_and_kwargs("chào", "briefing") == ("chào", {})
