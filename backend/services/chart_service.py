"""Donut chart rendering for asset portfolio reports.

Renders a donut chart as PNG showing asset allocation by type,
with total value in the center and a legend on the right.
"""
import io
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend for server-side rendering

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

logger = logging.getLogger(__name__)

# Asset type display config: label, color, emoji
ASSET_TYPE_CONFIG: dict[str, dict] = {
    "real_estate": {"label": "Bất động sản", "color": "#4E79A7", "emoji": "🏠"},
    "stocks": {"label": "Chứng khoán", "color": "#F28E2B", "emoji": "📈"},
    "mutual_fund": {"label": "Chứng chỉ quỹ", "color": "#E15759", "emoji": "🏦"},
    "crypto": {"label": "Tiền số", "color": "#76B7B2", "emoji": "₿"},
    "life_insurance": {"label": "Bảo hiểm", "color": "#59A14F", "emoji": "🛡️"},
    "gold": {"label": "Vàng", "color": "#EDC948", "emoji": "🥇"},
    "cash": {"label": "Tiền mặt", "color": "#B07AA1", "emoji": "💵"},
}

# Fallback for unknown asset types
_DEFAULT_CONFIG = {"label": "Khác", "color": "#BAB0AC", "emoji": "📦"}


def _format_vnd(amount: float) -> str:
    """Format amount in VND with appropriate suffix."""
    if abs(amount) >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f} tỷ"
    if abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:.1f} triệu"
    if abs(amount) >= 1_000:
        return f"{amount / 1_000:.0f}k"
    return f"{amount:,.0f}"


def render_donut_chart(
    allocation: dict[str, float],
    allocation_values: dict[str, float],
    total_value: float,
    change_pct: float | None = None,
    net_worth: float | None = None,
    timestamp: str = "",
) -> bytes:
    """Render a donut chart as PNG bytes.

    Args:
        allocation: asset_type -> percentage (e.g. {"stocks": 35.2, ...})
        allocation_values: asset_type -> VND value (e.g. {"stocks": 150000000, ...})
        total_value: total portfolio value in VND
        change_pct: percentage change vs previous month (None if no prior data)
        net_worth: net worth (total assets - liabilities), None to skip
        timestamp: update timestamp string to show at bottom

    Returns:
        PNG image bytes
    """
    # Sort by value descending
    sorted_types = sorted(allocation.keys(), key=lambda k: allocation.get(k, 0), reverse=True)

    labels = []
    sizes = []
    colors = []
    legend_labels = []

    for asset_type in sorted_types:
        pct = allocation[asset_type]
        if pct <= 0:
            continue
        cfg = ASSET_TYPE_CONFIG.get(asset_type, _DEFAULT_CONFIG)
        labels.append(cfg["label"])
        sizes.append(pct)
        colors.append(cfg["color"])
        value = allocation_values.get(asset_type, 0)
        legend_labels.append(f'{cfg["emoji"]} {cfg["label"]}: {_format_vnd(value)} ({pct:.1f}%)')

    if not sizes:
        return _render_empty_chart()

    fig, ax = plt.subplots(1, 1, figsize=(8, 6), dpi=150)
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Draw donut
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        autopct=lambda pct: f"{pct:.1f}%" if pct >= 5 else "",
        startangle=90,
        pctdistance=0.8,
        wedgeprops={"width": 0.35, "edgecolor": "#1a1a2e", "linewidth": 2},
        textprops={"color": "white", "fontsize": 9, "fontweight": "bold"},
    )

    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(9)

    # Center text: total value + change
    center_lines = [f"{_format_vnd(total_value)}"]
    if change_pct is not None:
        arrow = "↑" if change_pct >= 0 else "↓"
        color = "#59A14F" if change_pct >= 0 else "#E15759"
        center_lines.append(f"{arrow} {abs(change_pct):.1f}%")

    ax.text(0, 0.06, center_lines[0], ha="center", va="center",
            fontsize=16, fontweight="bold", color="white")
    ax.text(0, -0.12, "Tổng tài sản", ha="center", va="center",
            fontsize=9, color="#aaaaaa")
    if len(center_lines) > 1:
        change_color = "#59A14F" if change_pct and change_pct >= 0 else "#E15759"
        ax.text(0, -0.28, center_lines[1], ha="center", va="center",
                fontsize=11, fontweight="bold", color=change_color)

    # Legend on the right
    legend = ax.legend(
        wedges,
        legend_labels,
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        fontsize=9,
        frameon=False,
        labelcolor="white",
    )

    # Net worth footer — ``Tổng tài sản`` is the canonical Vietnamese
    # label across the bot (matches the briefing template + menu copy).
    footer_parts = []
    if net_worth is not None:
        footer_parts.append(f"Tổng tài sản: {_format_vnd(net_worth)}")
    if timestamp:
        footer_parts.append(f"Cập nhật: {timestamp}")
    if footer_parts:
        fig.text(0.5, 0.02, " | ".join(footer_parts),
                 ha="center", fontsize=8, color="#888888")

    fig.tight_layout(rect=[0, 0.05, 1, 1])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _render_empty_chart() -> bytes:
    """Render a placeholder chart when user has no assets."""
    fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.text(0.5, 0.5, "Chưa có tài sản nào", ha="center", va="center",
            fontsize=16, color="#888888", transform=ax.transAxes)
    ax.text(0.5, 0.35, 'Gửi "Thêm tài sản" để bắt đầu', ha="center", va="center",
            fontsize=11, color="#666666", transform=ax.transAxes)
    ax.axis("off")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
