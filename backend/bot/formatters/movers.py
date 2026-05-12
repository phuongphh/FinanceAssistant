"""Shared rendering helpers for "what moved today" asset lists.

Used by the morning briefing, the Telegram ``Tài sản → Tổng tài sản``
menu, and any future surface that wants a compact human-readable line
like::

    +4.0% so với hôm qua — VIC +15.0% · MSB +2.0% · SJC +3.0% · BTC −1.2%

Keeps the wording (so với hôm qua, separators, signed pct) in one place
so the three surfaces stay byte-consistent.
"""
from __future__ import annotations

from collections.abc import Iterable

from backend.wealth.services.net_worth_calculator import AssetMover

# Short, friendly type labels — falls back to the asset's own name
# when the user named the holding clearly (e.g. "Vàng SJC").
_TYPE_LABEL = {
    "stock": "",  # show ticker/name directly — "VIC +2%"
    "crypto": "",
    "gold": "Vàng",
    "cash": "Tiền mặt",
    "real_estate": "BĐS",
    "savings": "Tiết kiệm",
}


def _signed_pct(pct: float) -> str:
    if pct >= 0:
        return f"+{pct:.1f}%"
    # Use a real minus sign — looks nicer in proportional Telegram fonts
    # than a hyphen and matches the dashboard hero rendering.
    return f"−{abs(pct):.1f}%"


def _mover_label(mover: AssetMover) -> str:
    """Pick the most recognisable label for one asset in a compact list."""
    name = (mover.name or "").strip()
    prefix = _TYPE_LABEL.get(mover.asset_type, "")
    if not name:
        return prefix or mover.asset_type
    # For asset types where the name is usually a ticker (stock, crypto)
    # or already self-describing ("Vàng SJC"), drop the prefix.
    if not prefix or prefix.lower() in name.lower():
        return name
    return f"{prefix} {name}"


def format_movers_line(
    movers: Iterable[AssetMover],
    *,
    limit: int = 6,
) -> str:
    """Format a one-line summary of biggest movers, comma-separated.

    Empty input → ``""`` (caller decides whether to render a fallback).
    Output preserves sort order; truncates at ``limit`` to keep the line
    readable on mobile.
    """
    items = list(movers)[:limit]
    if not items:
        return ""
    parts = [f"{_mover_label(m)} {_signed_pct(m.change_percentage)}" for m in items]
    return " · ".join(parts)


def format_movers_block(
    total_pct: float | None,
    movers: Iterable[AssetMover],
    *,
    limit: int = 6,
) -> str:
    """Format the headline + per-asset breakdown across two lines.

    Example::

        📊 +4.0% so với hôm qua
        VIC +15.0% · MSB +2.0% · BTC −1.2%

    When ``total_pct`` is ``None`` (e.g. no baseline) the headline is
    omitted; when there are no movers the breakdown line is omitted.
    """
    lines: list[str] = []
    if total_pct is not None and abs(total_pct) >= 0.05:
        icon = "📈" if total_pct > 0 else "📉"
        lines.append(f"{icon} {_signed_pct(total_pct)} so với hôm qua")
    elif total_pct is not None:
        lines.append("➖ Đi ngang so với hôm qua")
    detail = format_movers_line(movers, limit=limit)
    if detail:
        lines.append(detail)
    return "\n".join(lines)
