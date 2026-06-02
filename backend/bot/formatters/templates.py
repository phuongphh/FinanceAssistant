"""Templates cho mọi tin nhắn bot gửi.

Nguyên tắc: Một function = một loại tin nhắn.
"""

from datetime import date, datetime
from functools import lru_cache
from html import escape as _html_escape
from pathlib import Path
from typing import Any

import yaml

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.bot.formatters.progress_bar import make_category_bar, make_progress_bar
from backend.config.categories import get_category
from backend.utils.time_vn import to_vn as _as_vn_time

_TRANSACTION_COPY_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "transaction_copy.yaml"
)


@lru_cache(maxsize=1)
def _transaction_copy() -> dict[str, Any]:
    with open(_TRANSACTION_COPY_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _confirmation_copy(key: str, default: str = "") -> str:
    return _transaction_copy().get("confirmation", {}).get(key, default)


def format_transaction_confirmation(
    merchant: str,
    amount: float,
    category_code: str,
    location: str | None = None,
    time: datetime | None = None,
    daily_spent: float | None = None,
    daily_budget: float | None = None,
    source_label: str | None = None,
    show_edit_hint: bool = False,
    transaction_type: str = "expense",
) -> str:
    """Tin nhắn xác nhận sau khi ghi giao dịch thành công.

    Output mẫu:
        ✅ Ghi xong!

        🍜 Phở Bát Đàn  —  45,000đ
        📍 Hà Nội  •  12:15

        💰 Hôm nay: 215k / 400k
           █████░░░░░ 54%

        Còn 185k cho hôm nay 👌
    """
    cat = get_category(category_code)

    title = _confirmation_copy("title_done", "✅ Đã ghi xong!")
    lines: list[str] = [title, ""]
    lines.append(
        f"{cat.emoji} {_html_escape(merchant)}  —  {format_money_full(amount)}"
    )

    context_parts: list[str] = []
    if location:
        context_parts.append(f"📍 {_html_escape(location)}")
    time_vn = _as_vn_time(time)
    if time_vn:
        context_parts.append(time_vn.strftime("%H:%M"))
    if context_parts:
        lines.append("  •  ".join(context_parts))

    is_money_in = transaction_type == "money_in"

    if source_label:
        if is_money_in:
            source_template = _confirmation_copy(
                "source_prefix_money_in", "💰 Nhận vào: {source}"
            )
        else:
            source_template = _confirmation_copy(
                "source_prefix", "💳 Chi từ: {source}"
            )
        lines.append(source_template.format(source=_html_escape(source_label)))

    if daily_spent is not None and daily_budget is not None and daily_budget > 0:
        lines.append("")
        bar = make_progress_bar(daily_spent, daily_budget, width=10)
        lines.append(
            f"💰 Hôm nay: {format_money_short(daily_spent)} / "
            f"{format_money_short(daily_budget)}"
        )
        lines.append(f"   {bar}")
        lines.append("")

        remaining = daily_budget - daily_spent
        if remaining > 0:
            lines.append(f"Còn {format_money_short(remaining)} cho hôm nay 👌")
        elif remaining > -100_000:
            lines.append(f"Đã vượt ngân sách {format_money_short(-remaining)} 🫣")
        else:
            lines.append(
                f"Vượt ngân sách {format_money_short(-remaining)} — cần chú ý 😅"
            )

    if show_edit_hint:
        hint_key = "edit_hint_money_in" if is_money_in else "edit_hint"
        hint = _confirmation_copy(hint_key) or _confirmation_copy("edit_hint")
        if hint:
            lines.append("")
            lines.append(hint.strip())

    return "\n".join(lines)


def format_receipt_confirmation(
    merchant: str,
    amount: float,
    category_code: str,
    receipt_date: date | None = None,
    items: list[tuple[str, float | None]] | None = None,
    confidence: str = "high",
    note: str | None = None,
    category_uncertain: bool = False,
) -> str:
    """Body of the confirmation message for an OCR receipt pending confirm.

    Renders the parsed facts (merchant, amount, date, category, note,
    item list). The caller owns the trailing call-to-action and the
    inline keyboard so the prompt always matches the buttons shown.

    ``note`` surfaces the receipt's "Lời nhắn"/transfer memo so it isn't
    silently dropped. ``category_uncertain`` switches the category line to
    an invitation to pick when we couldn't confidently auto-categorize.
    """
    cat = get_category(category_code)

    lines: list[str] = ["🧾 Đã đọc hoá đơn!", ""]
    lines.append(f"{cat.emoji} {merchant}  —  {format_money_full(amount)}")

    if receipt_date:
        lines.append(f"📅 {receipt_date.strftime('%d/%m/%Y')}")

    if category_uncertain:
        lines.append("🏷 Danh mục: bạn chọn giúp mình bên dưới nhé 👇")
    else:
        lines.append(f"🏷 Danh mục: {cat.name_vi}")

    if note:
        lines.append(f"📝 Nội dung: {note}")

    if items:
        lines.append("")
        lines.append("Chi tiết:")
        for name, price in items[:5]:
            name = (name or "").strip()
            if not name:
                continue
            if price:
                lines.append(f"• {name}  —  {format_money_short(float(price))}")
            else:
                lines.append(f"• {name}")
        if len(items) > 5:
            lines.append(f"… và {len(items) - 5} món khác")

    if confidence == "low":
        lines.append("")
        lines.append("⚠️ Mình đọc chưa chắc — bạn rà lại số tiền giúp nhé.")

    return "\n".join(lines)


def format_transaction_batch_confirmation(
    items: list[tuple[str, float, str]],
    time: datetime | None = None,
    source_label: str | None = None,
    show_edit_hint: bool = False,
) -> str:
    """Tin nhắn xác nhận sau khi ghi nhiều giao dịch cùng lúc."""
    total = sum(amount for _, amount, _ in items)
    title_template = _confirmation_copy(
        "batch_title", "✅ Đã ghi xong {count} khoản!"
    )
    lines: list[str] = [title_template.format(count=len(items)), ""]

    for merchant, amount, category_code in items:
        cat = get_category(category_code)
        lines.append(
            f"{cat.emoji} {_html_escape(merchant)}  —  {format_money_full(amount)}"
        )

    lines.append("")
    lines.append(f"Tổng: {format_money_full(total)}")
    time_vn = _as_vn_time(time)
    if time_vn:
        lines.append(time_vn.strftime("%H:%M"))

    if source_label:
        source_template = _confirmation_copy(
            "source_prefix", "💳 Chi từ: {source}"
        )
        lines.append(source_template.format(source=_html_escape(source_label)))

    if show_edit_hint:
        hint = _confirmation_copy("edit_hint")
        if hint:
            lines.append("")
            lines.append(hint.strip())

    return "\n".join(lines)


def format_daily_summary(
    date: datetime,
    total_spent: float,
    transaction_count: int,
    breakdown: list[tuple[str, float]],
    vs_average_pct: float | None = None,
) -> str:
    """Báo cáo cuối ngày.

    Output mẫu:
        🌙 Tóm tắt ngày 15/04

        Tổng chi: 485,000đ (4 giao dịch)

        🍜 Ăn uống      245k  ████████░░
        🚗 Di chuyển    150k  █████░░░░░
        👕 Mua sắm       90k  ███░░░░░░░

        So với trung bình: +12% ↑
    """
    lines: list[str] = [
        f"🌙 Tóm tắt ngày {date.strftime('%d/%m')}",
        "",
        f"Tổng chi: {format_money_full(total_spent)} ({transaction_count} giao dịch)",
        "",
    ]

    if breakdown:
        breakdown_sorted = sorted(breakdown, key=lambda x: x[1], reverse=True)
        max_amount = breakdown_sorted[0][1]

        for cat_code, amount in breakdown_sorted[:5]:
            cat = get_category(cat_code)
            bar = make_category_bar(amount, max_amount, width=10)
            name_padded = f"{cat.emoji} {cat.name_vi}".ljust(15)
            amount_str = format_money_short(amount).rjust(5)
            lines.append(f"{name_padded} {amount_str}  {bar}")

        lines.append("")

    if vs_average_pct is not None:
        if vs_average_pct > 0:
            lines.append(f"So với trung bình: +{vs_average_pct:.0f}% ↑")
        elif vs_average_pct < 0:
            lines.append(f"So với trung bình: {vs_average_pct:.0f}% ↓")
        else:
            lines.append("So với trung bình: tương đương")

    return "\n".join(lines).rstrip()


def format_budget_alert(
    category_code: str,
    spent: float,
    budget: float,
    days_left: int,
) -> str:
    """Cảnh báo khi gần/vượt ngân sách category."""
    cat = get_category(category_code)
    pct = (spent / budget * 100) if budget > 0 else 0

    if pct >= 100:
        emoji = "🚨"
        status = f"Đã vượt ngân sách {format_money_short(spent - budget)}"
    elif pct >= 90:
        emoji = "⚠️"
        status = f"Sắp chạm trần — còn {format_money_short(budget - spent)}"
    else:
        emoji = "📊"
        status = f"Còn {format_money_short(budget - spent)}"

    lines = [
        f"{emoji} Cảnh báo ngân sách",
        "",
        f"{cat.emoji} {cat.name_vi}",
        f"Đã chi: {format_money_short(spent)} / {format_money_short(budget)}",
        make_progress_bar(spent, budget, width=10),
        "",
        status,
        f"Còn {days_left} ngày nữa hết tháng",
    ]
    return "\n".join(lines)


def format_welcome_message(display_name: str | None = None) -> str:
    """Tin nhắn chào đầu tiên khi user gõ /start.

    Phase 2 sẽ mở rộng thành full onboarding.
    """
    greeting = f"Chào {display_name}!" if display_name else "Chào bạn!"

    return (
        f"👋 {greeting}\n\n"
        "Mình là trợ lý tài chính của bạn.\n"
        "Mình không chỉ ghi chép — mình hiểu bạn.\n\n"
        "Thử ngay nhé:\n"
        '• Gõ "45k phở" để ghi giao dịch\n'
        "• Gửi ảnh hóa đơn\n"
        "• Gửi voice message\n\n"
        "Hoặc tap /menu để xem hướng dẫn đầy đủ 💪"
    )
