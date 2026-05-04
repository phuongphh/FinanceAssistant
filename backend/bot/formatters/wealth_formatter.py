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
    """Confirmation after a wizard creates an asset.

    For assets with both purchase and current price (stocks, real estate
    where user gave a different "current" estimate), shows an unrealised
    gain/loss line. Skipped when current == initial so the cash flow and
    "use same price" stock flow stay one-line.

    Foreign-currency assets get an extra "≈ $X (FX rate, tạm tính)"
    line so the user sees both the native USD value they typed and the
    estimated VND that's actually stored.
    """
    icon = get_subtype_icon(asset.asset_type, asset.subtype)
    label = get_label(asset.asset_type)
    initial = Decimal(asset.initial_value or 0)
    current = Decimal(asset.current_value or 0)
    lines = [
        f"✅ Đã ghi {icon} {asset.name}",
        f"   {label}: {format_money_full(current)}",
    ]

    extra = asset.extra or {}
    if extra.get("currency") == "USD":
        current_usd = extra.get("current_value_usd")
        fx_rate = extra.get("fx_rate_vnd")
        if current_usd is not None and fx_rate:
            usd_str = _format_usd_short(Decimal(str(current_usd)))
            lines.append(
                f"   ≈ {usd_str} USD (FX {int(fx_rate):,} VND/USD, tạm tính)"
            )

    diff = current - initial
    if diff > 0:
        lines.append(f"   📈 +{format_money_short(diff)}")
    elif diff < 0:
        # format_money_short(-2_000_000) returns "-2tr" — sign baked in.
        lines.append(f"   📉 {format_money_short(diff)}")
    lines.append("")
    lines.append(f"💎 Tổng tài sản: <b>{format_money_full(net_worth)}</b>")
    return "\n".join(lines)


def _format_usd_short(amount: Decimal) -> str:
    """Render USD with US thousands separator; drop ``.00`` on whole values."""
    value = float(amount)
    if value == int(value):
        return f"${int(value):,}"
    return f"${value:,.2f}"


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
