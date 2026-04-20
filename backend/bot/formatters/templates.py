"""Templates cho mọi tin nhắn bot gửi.

Nguyên tắc: Một function = một loại tin nhắn.
"""
from datetime import datetime

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.bot.formatters.progress_bar import make_category_bar, make_progress_bar
from backend.config.categories import get_category


def format_transaction_confirmation(
    merchant: str,
    amount: float,
    category_code: str,
    location: str | None = None,
    time: datetime | None = None,
    daily_spent: float | None = None,
    daily_budget: float | None = None,
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

    lines: list[str] = ["✅ Ghi xong!", ""]
    lines.append(f"{cat.emoji} {merchant}  —  {format_money_full(amount)}")

    context_parts: list[str] = []
    if location:
        context_parts.append(f"📍 {location}")
    if time:
        context_parts.append(time.strftime("%H:%M"))
    if context_parts:
        lines.append("  •  ".join(context_parts))

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
        "• Gõ \"45k phở\" để ghi giao dịch\n"
        "• Gửi ảnh hóa đơn\n"
        "• Gửi voice message\n\n"
        "Hoặc tap /menu để xem hướng dẫn đầy đủ 💪"
    )
