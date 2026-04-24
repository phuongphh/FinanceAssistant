"""Portfolio pie/donut chart generator for Telegram asset reports.

Dark theme matching the mini-app:
  background  #17212b  (Telegram dark)
  card        #242f3d
  accent      #4ECDC4  (teal)

Public API
----------
generate_portfolio_chart(assets_data, *, change_pct, timestamp) -> bytes
"""
import io
import logging
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # non-interactive, must come before pyplot import

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

logger = logging.getLogger(__name__)

# ── Palette ─────────────────────────────────────────────────────────────────
_BG      = "#17212b"
_CARD    = "#242f3d"
_TEAL    = "#4ECDC4"
_WHITE   = "#ffffff"
_MUTED   = "#99a6b3"
_GREEN   = "#4CAF50"
_RED     = "#E15759"

# Asset type catalogue
_ASSET_CFG: dict[str, dict] = {
    "real_estate":    {"label": "Bất động sản",   "color": "#4ECDC4"},
    "stocks":         {"label": "Chứng khoán",    "color": "#F28E2B"},
    "mutual_fund":    {"label": "Chứng chỉ quỹ", "color": "#E15759"},
    "crypto":         {"label": "Tiền số",         "color": "#76B7B2"},
    "life_insurance": {"label": "Bảo hiểm",       "color": "#59A14F"},
    "gold":           {"label": "Vàng",            "color": "#EDC948"},
    "cash":           {"label": "Tiền mặt",        "color": "#B07AA1"},
}
_EXTRA_COLORS = ["#FF6B6B", "#A8E6CF", "#FFD93D", "#C3B1E1", "#FAD7A0"]
_DEFAULT_CFG  = {"label": "Khác", "color": "#BAB0AC"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(amount: float) -> str:
    """Format a VND amount with readable suffix."""
    a = abs(amount)
    sign = "" if amount >= 0 else "-"
    if a >= 1_000_000_000:
        return f"{sign}{a / 1_000_000_000:.1f} tỷ"
    if a >= 1_000_000:
        return f"{sign}{a / 1_000_000:.1f} triệu"
    if a >= 1_000:
        return f"{sign}{a / 1_000:.0f}k"
    return f"{sign}{a:,.0f}"


def _cfg_for(asset_type: str, extra_idx: int) -> dict:
    if asset_type in _ASSET_CFG:
        return _ASSET_CFG[asset_type]
    return {
        "label": asset_type.replace("_", " ").title(),
        "color": _EXTRA_COLORS[extra_idx % len(_EXTRA_COLORS)],
    }


# ── Main renderer ────────────────────────────────────────────────────────────

def generate_portfolio_chart(
    assets_data: list[dict],
    *,
    change_pct: float | None = None,
    timestamp: str = "",
) -> bytes:
    """Render a portfolio donut chart as PNG bytes.

    Args:
        assets_data: list of dicts, each with:
            ``asset_type`` (str) — key into _ASSET_CFG or any custom string
            ``value``      (float) — market value in VND
        change_pct: % change vs previous period; None to omit.
        timestamp: footer timestamp string (e.g. "07:00 24/04/2026").

    Returns:
        PNG image as bytes.
    """
    if not assets_data:
        return _empty_chart()

    # Aggregate by type
    totals: dict[str, float] = {}
    for item in assets_data:
        t = str(item.get("asset_type", "other"))
        totals[t] = totals.get(t, 0.0) + float(item.get("value", 0))

    grand_total = sum(totals.values())
    if grand_total <= 0:
        return _empty_chart()

    sorted_types = sorted(totals, key=totals.__getitem__, reverse=True)

    extra_idx = 0
    cfg_map: dict[str, dict] = {}
    for t in sorted_types:
        if t in _ASSET_CFG:
            cfg_map[t] = _ASSET_CFG[t]
        else:
            cfg_map[t] = {
                "label": t.replace("_", " ").title(),
                "color": _EXTRA_COLORS[extra_idx % len(_EXTRA_COLORS)],
            }
            extra_idx += 1

    sizes  = [totals[t] / grand_total * 100 for t in sorted_types]
    colors = [cfg_map[t]["color"] for t in sorted_types]
    values = [totals[t] for t in sorted_types]
    n      = len(sorted_types)

    # ── Figure ───────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(10, 6), dpi=150)
    fig.patch.set_facecolor(_BG)

    # Thin teal accent bar at top
    ax_bar = fig.add_axes([0.0, 0.972, 1.0, 0.028])
    ax_bar.set_facecolor(_TEAL)
    ax_bar.axis("off")

    # Header
    fig.text(0.04, 0.945, "Báo cáo danh mục tài sản",
             ha="left", va="top", fontsize=13, fontweight="bold", color=_WHITE)
    today_str = datetime.now().strftime("%d/%m/%Y")
    fig.text(0.96, 0.945, today_str,
             ha="right", va="top", fontsize=10, color=_MUTED)

    # GridSpec: left = donut, right = legend
    gs = GridSpec(
        1, 2,
        width_ratios=[1, 1.2],
        left=0.01, right=0.98,
        bottom=0.10, top=0.90,
        wspace=0.04,
        figure=fig,
    )

    # ── Donut chart ──────────────────────────────────────────────────────
    ax_d = fig.add_subplot(gs[0])
    ax_d.set_facecolor(_BG)

    wedges, _, pct_txts = ax_d.pie(
        sizes,
        colors=colors,
        startangle=90,
        autopct=lambda p: f"{p:.0f}%" if p >= 6 else "",
        pctdistance=0.78,
        wedgeprops={"width": 0.42, "edgecolor": _BG, "linewidth": 3},
        textprops={"color": _WHITE, "fontsize": 8, "fontweight": "bold"},
    )
    for txt in pct_txts:
        txt.set_fontsize(8)

    # Center text — total value
    ax_d.text(0, 0.15, _fmt(grand_total),
              ha="center", va="center",
              fontsize=17, fontweight="bold", color=_WHITE)
    ax_d.text(0, -0.07, "Tổng tài sản",
              ha="center", va="center",
              fontsize=9, color=_MUTED)

    # Change indicator inside donut
    if change_pct is not None:
        arrow = "▲" if change_pct >= 0 else "▼"
        c_clr = _GREEN if change_pct >= 0 else _RED
        ax_d.text(0, -0.30, f"{arrow} {abs(change_pct):.1f}%",
                  ha="center", va="center",
                  fontsize=11, fontweight="bold", color=c_clr)
        ax_d.text(0, -0.48, "so với tháng trước",
                  ha="center", va="center",
                  fontsize=8, color=_MUTED)

    # ── Legend with progress bars ────────────────────────────────────────
    ax_l = fig.add_subplot(gs[1])
    ax_l.set_facecolor(_BG)
    ax_l.set_xlim(0, 1)
    ax_l.set_ylim(0, 1)
    ax_l.axis("off")

    # Dynamic sizing so 7 items still fit
    slot_h     = 0.86 / max(n, 1)
    label_size = max(7.5, min(10.0, slot_h * 55))
    value_size = max(7.0, min(8.5,  slot_h * 47))
    pct_size   = max(8.0, min(11.0, slot_h * 60))
    bar_h      = max(0.012, slot_h * 0.18)
    dot_r      = max(0.010, slot_h * 0.10)

    y_top = 0.93

    for i, t in enumerate(sorted_types):
        pct   = sizes[i]
        val   = values[i]
        color = cfg_map[t]["color"]
        label = cfg_map[t]["label"]
        y     = y_top - i * slot_h

        # Color dot (circle marker)
        ax_l.plot(0.022, y - slot_h * 0.15, "o",
                  color=color, markersize=max(6, dot_r * 80),
                  clip_on=False, zorder=5)

        # Category label
        ax_l.text(0.065, y - slot_h * 0.04,
                  label,
                  ha="left", va="top",
                  fontsize=label_size, fontweight="600", color=_WHITE)

        # Value below label
        ax_l.text(0.065, y - slot_h * 0.30,
                  _fmt(val),
                  ha="left", va="top",
                  fontsize=value_size, color=_MUTED)

        # Percentage (right-aligned, colored)
        ax_l.text(0.98, y - slot_h * 0.10,
                  f"{pct:.1f}%",
                  ha="right", va="top",
                  fontsize=pct_size, fontweight="700", color=color)

        # Progress bar background
        bar_y   = y - slot_h * 0.60
        bar_xs  = 0.065
        bar_xe  = 0.97
        bar_w   = bar_xe - bar_xs

        ax_l.add_patch(mpatches.Rectangle(
            (bar_xs, bar_y), bar_w, bar_h,
            facecolor=_CARD, edgecolor="none", zorder=1,
        ))
        # Fill
        fill_w = (pct / 100) * bar_w
        if fill_w > 0.005:
            ax_l.add_patch(mpatches.Rectangle(
                (bar_xs, bar_y), fill_w, bar_h,
                facecolor=color, edgecolor="none", alpha=0.80, zorder=2,
            ))

    # ── Footer ───────────────────────────────────────────────────────────
    footer_parts = []
    if timestamp:
        footer_parts.append(f"Cập nhật: {timestamp}")
    if footer_parts:
        fig.text(0.5, 0.035, "  ·  ".join(footer_parts),
                 ha="center", va="bottom",
                 fontsize=8, color=_MUTED)

    # Subtle divider between header and chart area
    fig.add_axes([0.04, 0.916, 0.92, 0.001]).set_facecolor(_CARD)
    fig.axes[-1].axis("off")

    # ── Render ───────────────────────────────────────────────────────────
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=_BG, edgecolor="none", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _empty_chart() -> bytes:
    """Placeholder PNG when the user has no portfolio assets."""
    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)

    # Teal accent bar
    fig.add_axes([0.0, 0.96, 1.0, 0.04]).set_facecolor(_TEAL)
    fig.axes[-1].axis("off")

    ax.text(0.5, 0.58, "Chưa có tài sản nào",
            ha="center", va="center",
            fontsize=18, fontweight="bold", color=_MUTED,
            transform=ax.transAxes)
    ax.text(0.5, 0.42, 'Gửi "Thêm tài sản" để bắt đầu theo dõi 💪',
            ha="center", va="center",
            fontsize=12, color="#5a6a7a",
            transform=ax.transAxes)
    ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=_BG, edgecolor="none", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
