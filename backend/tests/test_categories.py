"""Tests for category config (Issue #26)."""
from backend.config.categories import (
    CATEGORIES,
    Category,
    get_all_categories,
    get_category,
)
from backend.config.emoji_map import EMOJI_MAP, get_emoji


EXPECTED_CODES = {
    "food", "transport", "housing", "shopping", "health", "education",
    "entertainment", "saving", "investment", "gift", "utility", "transfer",
    "other",
}


class TestCategoriesRegistry:
    def test_has_13_categories(self):
        assert len(CATEGORIES) == 13

    def test_covers_required_codes(self):
        assert set(CATEGORIES.keys()) == EXPECTED_CODES

    def test_each_category_has_required_fields(self):
        for code, cat in CATEGORIES.items():
            assert isinstance(cat, Category)
            assert cat.code == code
            assert cat.name_vi
            assert cat.emoji
            assert cat.color_hex.startswith("#") and len(cat.color_hex) == 7

    def test_color_hex_values_are_unique(self):
        colors = [cat.color_hex for cat in CATEGORIES.values()]
        assert len(colors) == len(set(colors))


class TestGetCategory:
    def test_food_emoji_and_color(self):
        cat = get_category("food")
        assert cat.emoji == "🍜"
        assert cat.color_hex == "#FF6B6B"
        assert cat.name_vi == "Ăn uống"

    def test_unknown_code_falls_back_to_other(self):
        cat = get_category("unknown")
        assert cat.code == "other"
        assert cat.emoji == "📌"

    def test_empty_string_falls_back_to_other(self):
        assert get_category("").code == "other"


class TestGetAllCategories:
    def test_returns_all_13(self):
        cats = get_all_categories()
        assert len(cats) == 13
        assert {c.code for c in cats} == EXPECTED_CODES

    def test_returns_list(self):
        assert isinstance(get_all_categories(), list)


class TestEmojiMap:
    def test_map_covers_all_categories(self):
        assert set(EMOJI_MAP.keys()) == EXPECTED_CODES

    def test_get_emoji_matches_category(self):
        assert get_emoji("food") == "🍜"
        assert get_emoji("transport") == "🚗"

    def test_get_emoji_unknown_falls_back(self):
        assert get_emoji("not_real") == "📌"
