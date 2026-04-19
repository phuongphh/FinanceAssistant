"""Re-export helper cho emoji map các category.

Dùng khi code chỉ cần map code -> emoji mà không cần full Category object.
"""
from backend.config.categories import CATEGORIES, Category, get_category

EMOJI_MAP: dict[str, str] = {code: cat.emoji for code, cat in CATEGORIES.items()}


def get_emoji(code: str) -> str:
    """Lấy emoji cho category code; fallback về emoji của 'other'."""
    return get_category(code).emoji


__all__ = ["EMOJI_MAP", "get_emoji", "Category", "get_category"]
