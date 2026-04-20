"""Định nghĩa categories và emoji cho toàn hệ thống.

Một category = một emoji cố định, nhất quán.
Mọi module khác (formatters, keyboards, Mini App) đều import từ đây.
Thêm category mới chỉ cần sửa file này.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    code: str           # Dùng trong DB, callback_data
    name_vi: str        # Hiển thị cho user VN
    emoji: str          # Emoji nhất quán
    color_hex: str      # Dùng trong Mini App charts


CATEGORIES: dict[str, Category] = {
    "food": Category("food", "Ăn uống", "🍜", "#FF6B6B"),
    "transport": Category("transport", "Di chuyển", "🚗", "#4ECDC4"),
    "housing": Category("housing", "Nhà cửa", "🏠", "#95E1D3"),
    "shopping": Category("shopping", "Mua sắm", "👕", "#F38181"),
    "health": Category("health", "Sức khỏe", "💊", "#AA96DA"),
    "education": Category("education", "Giáo dục", "📚", "#FCBAD3"),
    "entertainment": Category("entertainment", "Giải trí", "🎮", "#FFFFD2"),
    "saving": Category("saving", "Tiết kiệm", "💰", "#A8E6CF"),
    "investment": Category("investment", "Đầu tư", "📊", "#3D5A80"),
    "gift": Category("gift", "Quà tặng", "🎁", "#EE6C4D"),
    "utility": Category("utility", "Tiện ích", "⚡", "#F9ED69"),
    "transfer": Category("transfer", "Chuyển khoản", "🔄", "#B0B0B0"),
    "other": Category("other", "Khác", "📌", "#808080"),
}


def get_category(code: str) -> Category:
    """Lấy category; fallback về 'other' nếu không tìm thấy."""
    return CATEGORIES.get(code, CATEGORIES["other"])


def get_all_categories() -> list[Category]:
    """Trả về toàn bộ categories theo thứ tự định nghĩa."""
    return list(CATEGORIES.values())
