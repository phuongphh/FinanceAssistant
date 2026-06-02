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


# Income (money-in) categories — kept separate from spending buckets so the
# transaction category picker can offer the right taxonomy. Codes mirror the
# Mini App money-in labels (see backend/miniapp/routes.py) so both surfaces
# agree on what an income category means.
INCOME_CATEGORIES: dict[str, Category] = {
    "salary_bonus": Category("salary_bonus", "Lương/Thưởng", "💼", "#2E7D32"),
    "freelance_part_time": Category("freelance_part_time", "Freelance/Việc thêm", "🧑‍💻", "#388E3C"),
    "dividend": Category("dividend", "Cổ tức", "📈", "#43A047"),
    "saving_interest": Category("saving_interest", "Lãi tiết kiệm", "🏦", "#66BB6A"),
    "other_income": Category("other_income", "Khác", "💰", "#A8E6CF"),
}


def get_category(code: str) -> Category:
    """Lấy category; fallback về 'other' nếu không tìm thấy.

    Resolves both spending and income codes — a money-in transaction whose
    category is e.g. ``salary_bonus`` must still render its emoji/label.
    """
    if code in CATEGORIES:
        return CATEGORIES[code]
    if code in INCOME_CATEGORIES:
        return INCOME_CATEGORIES[code]
    return CATEGORIES["other"]


def get_all_categories() -> list[Category]:
    """Trả về toàn bộ spending categories theo thứ tự định nghĩa."""
    return list(CATEGORIES.values())


def get_all_income_categories() -> list[Category]:
    """Trả về toàn bộ income (money-in) categories theo thứ tự định nghĩa."""
    return list(INCOME_CATEGORIES.values())
