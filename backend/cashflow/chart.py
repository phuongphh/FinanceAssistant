"""Phase 4B S18 — Cashflow waterfall chart renderer.

Generates a 1000×600px PNG showing:
- Grouped bars: income (green #4CAF50) + expense (red #F44336) per month
- Line overlay: balance EOM (purple #7C4DFF)
- Net badge on each month group: "+5.2 tr" (green) | "−2.1 tr" (red)
- X-axis: "Tháng 8/2026", "Tháng 9/2026", "Tháng 10/2026"
- Y-axis: VND formatted as "tr" (triệu), "tỷ", or "tỷ" depending on scale
- Watermark: "dự báo dựa trên thu chi định kỳ"

Matplotlib is used (already in the project via market_data charts).
Non-interactive backend (Agg) so we can render in a background thread
without a display server.

Performance target: p95 < 500ms on a single-core VPS.

Layer contract: pure computation — no DB, no Telegram. Returns bytes.
"""
from __future__ import annotations

import io
import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Colour palette — chosen for contrast on Telegram's light/dark themes.
COLOR_INCOME = "#4CAF50"        # green
COLOR_EXPENSE = "#F44336"       # red
COLOR_BALANCE = "#7C4DFF"       # purple
COLOR_NET_POS = "#2E7D32"       # dark green text
COLOR_NET_NEG = "#C62828"       # dark red text
COLOR_WATERMARK = "#BDBDBD"     # light grey

CHART_WIDTH_PX = 1000
CHART_HEIGHT_PX = 600
DPI = 100   # → 10×6 inch figure


def render_cashflow_waterfall(
    monthly_data: list[dict[str, Any]],
) -> bytes:
    """Render the waterfall chart and return PNG bytes.

    ``monthly_data`` is a list of dicts matching ``MonthlyForecastData.to_dict()``:
    [{"month": "2026-11-01", "income": "20500000", "expense": "15300000",
      "net": "5200000", "balance_eom": "32000000"}, ...]
    """
    import matplotlib
    matplotlib.use("Agg")   # non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np

    if not monthly_data:
        return _empty_chart()

    months = [_parse_date(d["month"]) for d in monthly_data]
    incomes = [Decimal(str(d.get("income", 0))) for d in monthly_data]
    expenses = [Decimal(str(d.get("expense", 0))) for d in monthly_data]
    nets = [Decimal(str(d.get("net", 0))) for d in monthly_data]
    balances = [Decimal(str(d.get("balance_eom", 0))) for d in monthly_data]

    n = len(months)
    x = np.arange(n)
    width = 0.35

    fig, ax1 = plt.subplots(
        figsize=(CHART_WIDTH_PX / DPI, CHART_HEIGHT_PX / DPI),
        dpi=DPI,
    )

    # ── Grouped bars ────────────────────────────────────────────────────
    ax1.bar(
        x - width / 2, [float(v) for v in incomes],
        width, label="Thu nhập", color=COLOR_INCOME, alpha=0.85, zorder=3,
    )
    ax1.bar(
        x + width / 2, [float(v) for v in expenses],
        width, label="Chi tiêu", color=COLOR_EXPENSE, alpha=0.85, zorder=3,
    )

    # ── Balance line (right y-axis) ─────────────────────────────────────
    ax2 = ax1.twinx()
    ax2.plot(
        x, [float(v) for v in balances],
        color=COLOR_BALANCE, linewidth=2.5, marker="o", markersize=7,
        label="Số dư cuối tháng", zorder=4,
    )

    # ── Net badges above each group ─────────────────────────────────────
    max_val = max(
        max(float(v) for v in incomes) if incomes else 0,
        max(float(v) for v in expenses) if expenses else 0,
    )
    badge_y = max_val * 1.07 if max_val > 0 else 1_000_000
    for i, net in enumerate(nets):
        sign = "+" if net >= 0 else "−"
        color = COLOR_NET_POS if net >= 0 else COLOR_NET_NEG
        ax1.text(
            x[i], badge_y,
            f"{sign}{_fmt_short(abs(net))}",
            ha="center", va="bottom", fontsize=9, color=color,
            fontweight="bold", zorder=5,
        )

    # ── X-axis labels ───────────────────────────────────────────────────
    ax1.set_xticks(x)
    ax1.set_xticklabels(
        [f"Tháng {m.month}/{m.year}" for m in months],
        fontsize=11,
    )

    # ── Y-axis formatters ────────────────────────────────────────────────
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: _fmt_axis(v))
    )
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: _fmt_axis(v))
    )
    ax1.set_ylabel("Thu / Chi (VNĐ)", fontsize=10)
    ax2.set_ylabel("Số dư cuối tháng (VNĐ)", fontsize=10, color=COLOR_BALANCE)
    ax2.tick_params(axis="y", colors=COLOR_BALANCE)

    # ── Legend ──────────────────────────────────────────────────────────
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        handles1 + handles2, labels1 + labels2,
        loc="upper left", fontsize=9,
    )

    # ── Watermark ───────────────────────────────────────────────────────
    fig.text(
        0.5, 0.01,
        "dự báo dựa trên thu chi định kỳ",
        ha="center", va="bottom",
        fontsize=8, color=COLOR_WATERMARK,
        style="italic",
    )

    ax1.set_ylim(bottom=0)
    ax1.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)
    fig.tight_layout(rect=[0, 0.03, 1, 1])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_date(iso: str):
    from datetime import date
    return date.fromisoformat(iso)


def _fmt_short(amount: Decimal) -> str:
    """Format amount as short Vietnamese label: tỷ / tr / k."""
    v = float(amount)
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f} tỷ"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f} tr"
    if v >= 1_000:
        return f"{v / 1_000:.0f}k"
    return f"{v:.0f}"


def _fmt_axis(value: float) -> str:
    """Y-axis tick formatter — compact."""
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}tỷ"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.0f}tr"
    return f"{value / 1_000:.0f}k"


def _empty_chart() -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(CHART_WIDTH_PX / DPI, CHART_HEIGHT_PX / DPI), dpi=DPI)
    ax.text(0.5, 0.5, "Chưa có dữ liệu dự báo", ha="center", va="center",
            transform=ax.transAxes, fontsize=14, color="#9E9E9E")
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
