"""Format wealth-related Telegram messages.

Kept thin so handlers stay focused on flow control. Money formatting
goes through ``backend.bot.formatters.money`` so we have one canonical
short/full format across the bot.
"""
from __future__ import annotations

from decimal import Decimal

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.wealth.asset_types import get_icon, get_label
from backend.wealth.models.asset import Asset


def format_asset_added(asset: Asset, net_worth: Decimal) -> str:
    """Confirmation after a wizard creates an asset."""
    icon = get_icon(asset.asset_type)
    label = get_label(asset.asset_type)
    return (
        f"✅ Đã ghi {icon} {asset.name}\n"
        f"   {label}: {format_money_full(asset.current_value)}\n\n"
        f"💎 Tổng tài sản: <b>{format_money_full(net_worth)}</b>"
    )


def format_breakdown_lines(by_type: dict[str, Decimal]) -> str:
    """One line per asset type — icon, label, value, percentage."""
    if not by_type:
        return ""
    total = sum(by_type.values(), Decimal(0))
    if total == 0:
        return ""
    lines: list[str] = []
    sorted_items = sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)
    for asset_type, value in sorted_items:
        pct = float(value / total * 100)
        lines.append(
            f"{get_icon(asset_type)} {get_label(asset_type)}: "
            f"{format_money_short(value)} ({pct:.0f}%)"
        )
    return "\n".join(lines)
