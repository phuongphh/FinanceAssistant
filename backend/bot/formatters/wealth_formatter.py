"""Format wealth-related Telegram messages.

Kept thin so handlers stay focused on flow control. Money formatting
goes through ``backend.bot.formatters.money`` so we have one canonical
short/full format across the bot.
"""
from __future__ import annotations

from decimal import Decimal

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.wealth.asset_types import get_icon, get_label, get_subtype_icon, get_subtype_label
from backend.wealth.models.asset import Asset


def format_asset_added(asset: Asset, net_worth: Decimal) -> str:
    """Confirmation after a wizard creates an asset."""
    icon = get_subtype_icon(asset.asset_type, asset.subtype)
    label = get_label(asset.asset_type)
    return (
        f"✅ Đã ghi {icon} {asset.name}\n"
        f"   {label}: {format_money_full(asset.current_value)}\n\n"
        f"💎 Tổng tài sản: <b>{format_money_full(net_worth)}</b>"
    )


def format_asset_list(assets: list[Asset]) -> str:
    """Telegram message for /taisan — all active assets + total."""
    if not assets:
        return (
            "📭 Bạn chưa có tài sản nào.\n\n"
            "Dùng /themtaisan để thêm tài sản đầu tiên!"
        )
    total = sum((a.current_value for a in assets), Decimal(0))
    lines: list[str] = [f"📊 <b>Tài sản của bạn</b> ({len(assets)} mục)\n"]
    for asset in assets:
        icon = get_subtype_icon(asset.asset_type, asset.subtype)
        subtype_label = get_subtype_label(asset.subtype)
        amount = format_money_short(asset.current_value)
        if subtype_label:
            lines.append(f"{icon} {asset.name} — {subtype_label} — {amount}")
        else:
            lines.append(f"{icon} {asset.name} — {amount}")
    lines.append(f"\n💎 Tổng: <b>{format_money_short(total)}</b>")
    return "\n".join(lines)


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
