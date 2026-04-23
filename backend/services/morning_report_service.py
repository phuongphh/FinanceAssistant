"""Morning report service — daily 7 AM portfolio summary.

Aggregates portfolio data, renders a donut chart, builds a text summary,
and sends everything to the user via Telegram.
"""
import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio_asset import PortfolioAsset
from backend.models.user import User
from backend.services.chart_service import ASSET_TYPE_CONFIG, render_donut_chart
from backend.services.portfolio_service import _compute_asset_fields, list_assets
from backend.ports.notifier import get_notifier

logger = logging.getLogger(__name__)

# Vietnamese day names
_WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

# Action buttons shown after the report
MORNING_REPORT_BUTTONS: list[list[dict]] = [
    [
        {"text": "➕ Thêm tài sản", "callback_data": "menu:income"},
        {"text": "📊 Báo cáo chi tiêu tháng này", "callback_data": "menu:report"},
    ],
    [
        {"text": "🔍 Xem cơ hội thị trường", "callback_data": "menu:market"},
        {"text": "🎯 Cập nhật mục tiêu tài chính", "callback_data": "menu:goals"},
    ],
]


def _format_vnd_text(amount: float) -> str:
    """Format VND amount for text summary."""
    if abs(amount) >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f} tỷ"
    if abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:.1f} triệu"
    if abs(amount) >= 1_000:
        return f"{amount / 1_000:.0f}k"
    return f"{amount:,.0f}"


async def _get_previous_month_total(
    db: AsyncSession, user_id: uuid.UUID
) -> float | None:
    """Estimate previous month's total portfolio value.

    Uses the oldest snapshot approach: if assets existed last month,
    approximate by using purchase_price * quantity for assets created
    before last month, plus current_price for newer ones.
    This is a best-effort estimate.
    """
    first_of_month = date.today().replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    # Get assets that existed before this month
    stmt = select(PortfolioAsset).where(
        PortfolioAsset.user_id == user_id,
        PortfolioAsset.deleted_at.is_(None),
        PortfolioAsset.created_at < first_of_month,
    )
    result = await db.execute(stmt)
    assets = list(result.scalars().all())

    if not assets:
        return None

    total = 0.0
    for asset in assets:
        quantity = float(asset.quantity) if asset.quantity is not None else 0.0
        # Use purchase_price as estimate for last month
        price = float(asset.purchase_price) if asset.purchase_price is not None else 0.0
        total += quantity * price

    return total if total > 0 else None


async def build_morning_report(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[bytes | None, str, bool]:
    """Build the morning report data.

    Returns:
        (chart_png_bytes, text_summary, has_assets)
        chart_png_bytes is None if user has no assets.
    """
    assets = await list_assets(db, user_id, limit=500)

    if not assets:
        return None, "", False

    # Aggregate by asset type
    allocation_values: dict[str, float] = {}
    total_value = 0.0

    for asset in assets:
        computed = _compute_asset_fields(asset)
        mv = computed["market_value"] or 0.0
        total_value += mv
        allocation_values[asset.asset_type] = (
            allocation_values.get(asset.asset_type, 0.0) + mv
        )

    # Compute percentages
    allocation_pct: dict[str, float] = {}
    if total_value > 0:
        allocation_pct = {
            k: round((v / total_value) * 100, 2)
            for k, v in allocation_values.items()
        }

    # Previous month comparison
    prev_total = await _get_previous_month_total(db, user_id)
    change_pct = None
    if prev_total and prev_total > 0:
        change_pct = round(((total_value - prev_total) / prev_total) * 100, 1)

    # Timestamp
    now = datetime.now()
    timestamp = now.strftime("%H:%M %d/%m/%Y")

    # Render chart
    chart_bytes = render_donut_chart(
        allocation=allocation_pct,
        allocation_values=allocation_values,
        total_value=total_value,
        change_pct=change_pct,
        net_worth=total_value,  # No liabilities tracking yet
        timestamp=timestamp,
    )

    # Build text summary
    text = _build_text_summary(
        allocation_values=allocation_values,
        allocation_pct=allocation_pct,
        total_value=total_value,
        change_pct=change_pct,
    )

    return chart_bytes, text, True


def _build_text_summary(
    allocation_values: dict[str, float],
    allocation_pct: dict[str, float],
    total_value: float,
    change_pct: float | None,
) -> str:
    """Build the text summary that accompanies the chart."""
    change_str = ""
    if change_pct is not None:
        arrow = "↑" if change_pct >= 0 else "↓"
        change_str = f" {arrow} {abs(change_pct):.1f}%"

    lines = [
        f"💰 Tổng tài sản: {_format_vnd_text(total_value)}{change_str}",
        f"📊 Tài sản ròng: {_format_vnd_text(total_value)}",
        "",
    ]

    # Sort by value descending
    sorted_types = sorted(
        allocation_values.keys(),
        key=lambda k: allocation_values[k],
        reverse=True,
    )

    for asset_type in sorted_types:
        cfg = ASSET_TYPE_CONFIG.get(asset_type, {"emoji": "📦", "label": asset_type})
        value = allocation_values[asset_type]
        pct = allocation_pct.get(asset_type, 0)
        lines.append(
            f'{cfg["emoji"]} {cfg["label"]}: {_format_vnd_text(value)} ({pct:.1f}%)'
        )

    return "\n".join(lines)


def _build_greeting() -> str:
    """Build the morning greeting message."""
    today = date.today()
    weekday = _WEEKDAYS[today.weekday()]
    date_str = today.strftime("%d/%m/%Y")
    return (
        f"🌅 Chào buổi sáng! Đây là báo cáo tài sản của bạn hôm nay.\n"
        f"📅 {weekday}, ngày {date_str}"
    )


def _build_no_assets_message() -> str:
    """Message for users with no portfolio assets."""
    today = date.today()
    weekday = _WEEKDAYS[today.weekday()]
    date_str = today.strftime("%d/%m/%Y")
    return (
        f"🌅 Chào buổi sáng! {weekday}, ngày {date_str}\n\n"
        f"Bạn chưa có tài sản nào trong danh mục.\n"
        f'Gửi "Thêm tài sản" để bắt đầu theo dõi tài chính nhé! 💪'
    )


async def send_morning_report(
    db: AsyncSession, user: User
) -> bool:
    """Send the morning report to a single user.

    Transport is resolved via the :class:`Notifier` port so this
    service stays testable without mocking HTTP: tests patch
    ``backend.ports.notifier.get_notifier`` with a fake that just
    records the outgoing messages.

    Returns True if dispatched (actual delivery status is the
    adapter's responsibility — we trust it has logged any failure).
    """
    notifier = get_notifier()
    chat_id = user.telegram_id

    chart_bytes, text_summary, has_assets = await build_morning_report(db, user.id)

    if not has_assets:
        # Send encouraging message instead of empty chart
        await notifier.send_message(chat_id, _build_no_assets_message())
        return True

    greeting = _build_greeting()

    # Send chart with greeting as caption
    caption = f"{greeting}\n\n{text_summary}"

    # Telegram caption limit is 1024 chars; if too long, send separately
    if len(caption) > 1024:
        await notifier.send_message(chat_id, greeting)
        await notifier.send_photo(chat_id, chart_bytes, caption="")
        await notifier.send_message(
            chat_id,
            text_summary,
            reply_markup={"inline_keyboard": MORNING_REPORT_BUTTONS},
        )
    else:
        await notifier.send_photo(
            chat_id,
            chart_bytes,
            caption=caption,
            reply_markup={"inline_keyboard": MORNING_REPORT_BUTTONS},
        )

    logger.info("Morning report sent to user %s (telegram: %s)", user.id, chat_id)
    return True
