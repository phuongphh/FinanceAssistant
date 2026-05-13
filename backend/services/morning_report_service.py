"""Morning report service — daily 7 AM portfolio summary.

Aggregates portfolio data, renders a donut chart, builds a text summary,
and sends everything to the user via Telegram.
"""
import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.ports.notifier import get_notifier
from backend.services.chart_generator import generate_portfolio_chart
from backend.wealth.asset_types import get_icon, get_label
from backend.wealth.services import asset_service, net_worth_calculator

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
    """Net worth at end of last month, sourced from asset_snapshots.

    Returns None when no snapshots exist before this month (new user or
    first run after data migration — show no change rather than wrong data).
    """
    first_of_month = date.today().replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    total = await net_worth_calculator.calculate_historical(db, user_id, last_month_end)
    return float(total) if total > 0 else None


async def build_morning_report(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[bytes | None, str, bool]:
    """Build the morning report data.

    Returns:
        (chart_png_bytes, text_summary, has_assets)
        chart_png_bytes is None if user has no assets or chart fails.
    """
    assets = await asset_service.get_user_assets(db, user_id)

    if not assets:
        return None, "", False

    # Aggregate by asset type using current_value directly (no qty × price)
    allocation_values: dict[str, float] = {}
    total_value = 0.0

    for asset in assets:
        mv = float(asset.current_value or 0)
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

    # Render chart (fallback to None on failure)
    assets_data = [
        {"asset_type": t, "value": v}
        for t, v in allocation_values.items()
    ]
    try:
        chart_bytes = generate_portfolio_chart(
            assets_data,
            change_pct=change_pct,
            timestamp=timestamp,
        )
    except (ValueError, RuntimeError, OSError):
        logger.exception("Chart generation failed for user %s — will send text only", user_id)
        chart_bytes = None

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

    # One headline: ``Tổng tài sản`` is the canonical Vietnamese label for
    # net worth across the bot. The redundant "Tài sản ròng" line that
    # showed the same number was confusing — re-introduce only when the
    # liabilities model lands and the two values can actually differ.
    lines = [
        f"💰 Tổng tài sản: {_format_vnd_text(total_value)}{change_str}",
        "",
    ]

    # Sort by value descending
    sorted_types = sorted(
        allocation_values.keys(),
        key=lambda k: allocation_values[k],
        reverse=True,
    )

    for asset_type in sorted_types:
        icon = get_icon(asset_type)
        label = get_label(asset_type)
        # ``get_label`` returns the raw key when an asset_type isn't in
        # ``content/asset_categories.yaml``. That happens if a row was
        # written via the legacy V1 portfolio API (plurals like
        # "stocks") and never migrated. Log so we can spot the drift
        # in production without surfacing ugly text to the user.
        if label == asset_type:
            logger.warning(
                "morning_report: asset_type %r missing from asset_categories.yaml — "
                "rendered as raw key", asset_type,
            )
        value = allocation_values[asset_type]
        pct = allocation_pct.get(asset_type, 0)
        lines.append(f"{icon} {label}: {_format_vnd_text(value)} ({pct:.1f}%)")

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
        await notifier.send_message(chat_id, _build_no_assets_message())
        return True

    greeting = _build_greeting()

    if chart_bytes is None:
        # Chart failed — send text-only fallback
        await notifier.send_message(
            chat_id,
            f"{greeting}\n\n{text_summary}",
            reply_markup={"inline_keyboard": MORNING_REPORT_BUTTONS},
        )
    else:
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
