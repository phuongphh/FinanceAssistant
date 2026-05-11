"""Matplotlib-backed chart rendering adapter for Financial Twin.

This is intentionally the only module that imports matplotlib. Services and
handlers depend on the plain ``render_cone_chart`` function returning PNG bytes,
which keeps future renderer swaps isolated.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml

_COPY_PATH = Path(__file__).resolve().parents[2] / "content" / "twin_copy.yaml"


def _load_copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["chart"]


def _money_vnd(value: Decimal | int | float | str) -> str:
    amount = float(Decimal(str(value)))
    if abs(amount) >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f} tỷ"
    if abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:.0f} triệu"
    return f"{amount:,.0f}đ"


def _series(cone: list[dict[str, Any]], key: str) -> list[float]:
    return [float(Decimal(str(point[key]))) for point in cone]


def _load_life_event_chart_copy() -> dict[str, Any]:
    """Lazy-load life-event chart copy. Distinct from twin_copy.yaml."""
    path = Path(__file__).resolve().parents[2] / "content" / "life_events.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["chart"]


def render_life_event_impact_chart(
    *,
    before_cone: list[dict[str, Any]],
    after_cone: list[dict[str, Any]],
    base_year: int,
    title: str,
    impact_labels: list[tuple[int, str]] | None = None,
    width: int = 1000,
    height: int = 600,
) -> bytes:
    """Render "Before vs After" cones as a single PNG.

    Args:
        before_cone: pristine cone (no events applied) — drawn in calm blue.
        after_cone: cone with this event applied — drawn in warm orange.
        base_year: calendar year for column 0 (e.g. 2026). Used for x-axis labels.
        title: chart title (already localized).
        impact_labels: list of (year_idx, label) annotations at milestones.
        width, height: pixel dimensions.

    Both cones share the same year index range, so we draw the after cone on
    top with slight transparency. The PNG is suitable for Telegram and
    Mini App. Designed to render in < 500 ms on commodity hardware (single
    fill_between + plot pair per cone).
    """
    if not before_cone:
        raise ValueError("before_cone must not be empty")
    if not after_cone:
        raise ValueError("after_cone must not be empty")

    copy = _load_life_event_chart_copy()
    years_idx = [int(point["year"]) for point in before_cone]
    cal_years = [base_year + idx for idx in years_idx]

    before_p10 = _series(before_cone, "p10")
    before_p50 = _series(before_cone, "p50")
    before_p90 = _series(before_cone, "p90")
    after_by_year = {int(p["year"]): p for p in after_cone}
    after_years_idx = [idx for idx in years_idx if idx in after_by_year]
    after_cal_years = [base_year + idx for idx in after_years_idx]
    after_p10 = [float(Decimal(str(after_by_year[idx]["p10"]))) for idx in after_years_idx]
    after_p50 = [float(Decimal(str(after_by_year[idx]["p50"]))) for idx in after_years_idx]
    after_p90 = [float(Decimal(str(after_by_year[idx]["p90"]))) for idx in after_years_idx]

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor("#fffaf2")
    ax.set_facecolor("#fffaf2")

    # Before: calm blue.
    ax.fill_between(
        cal_years, before_p10, before_p90, color="#4285F4", alpha=0.30,
        label=copy["cone_before_label"],
    )
    ax.plot(
        cal_years, before_p50, color="#1a73e8", linewidth=2.2, linestyle="-",
        label=copy["p50_before_label"],
    )
    # After: warm orange.
    ax.fill_between(
        after_cal_years, after_p10, after_p90, color="#FF9800", alpha=0.30,
        label=copy["cone_after_label"].format(title=title),
    )
    ax.plot(
        after_cal_years, after_p50, color="#E65100", linewidth=2.2, linestyle="--",
        label=copy["p50_after_label"],
    )

    if impact_labels:
        for year_idx, label in impact_labels:
            if year_idx >= len(cal_years):
                continue
            x = base_year + year_idx
            # Annotate at the after-cone P50 so impact context is anchored to
            # the modified projection.
            y = after_p50[after_years_idx.index(year_idx)] if year_idx in after_years_idx else before_p50[year_idx]
            ax.annotate(
                label,
                xy=(x, y),
                xytext=(0, 14),
                textcoords="offset points",
                ha="center",
                fontsize=9,
                color="#bf360c",
                bbox={"boxstyle": "round,pad=0.3", "fc": "#fff3e0", "ec": "#FF9800", "lw": 0.8},
            )

    ax.set_title(title, fontsize=14, fontweight="bold", color="#243b53", pad=14)
    ax.set_xlabel(copy["x_label"], fontsize=11)
    ax.set_ylabel(copy["y_label"], fontsize=11)
    ax.yaxis.set_major_formatter(lambda value, _pos: _money_vnd(value))
    ax.grid(True, color="#d9e2ec", linewidth=0.8, alpha=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    ax.text(
        0.5,
        0.02,
        copy["watermark"],
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=9,
        color="#627d98",
        alpha=0.9,
    )

    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def render_cone_chart(
    cone: list[dict[str, Any]],
    optimal: list[dict[str, Any]] | None = None,
    *,
    width: int = 800,
    height: int = 600,
) -> bytes:
    """Render P10/P50/P90 cone as PNG bytes."""
    if not cone:
        raise ValueError("cone must not be empty")

    copy = _load_copy()
    years = [int(point["year"]) for point in cone]
    p10 = _series(cone, "p10")
    p50 = _series(cone, "p50")
    p90 = _series(cone, "p90")

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor("#fffaf2")
    ax.set_facecolor("#fffaf2")

    ax.fill_between(
        years, p10, p90, color="#8ecae6", alpha=0.35, label=copy["cone_label"]
    )
    ax.plot(years, p50, color="#126782", linewidth=2.6, label=copy["p50_label"])
    ax.scatter(
        [years[0]],
        [p50[0]],
        color="#ffb703",
        s=45,
        zorder=4,
        label=copy["current_label"],
    )

    if optimal:
        opt_by_year = {int(point["year"]): point for point in optimal}
        opt_years = [y for y in years if y in opt_by_year]
        if opt_years:
            opt_p10 = [float(Decimal(str(opt_by_year[y]["p10"]))) for y in opt_years]
            opt_p50 = [float(Decimal(str(opt_by_year[y]["p50"]))) for y in opt_years]
            opt_p90 = [float(Decimal(str(opt_by_year[y]["p90"]))) for y in opt_years]
            ax.fill_between(
                opt_years,
                opt_p10,
                opt_p90,
                color="#2a9d8f",
                alpha=0.16,
                label=copy["optimal_cone_label"],
            )
            ax.plot(
                opt_years,
                opt_p50,
                color="#2a9d8f",
                linewidth=2.1,
                linestyle="--",
                label=copy["optimal_label"],
            )

    ax.set_title(copy["title"], fontsize=15, fontweight="bold", color="#243b53", pad=16)
    ax.set_xlabel(copy["x_label"], fontsize=11)
    ax.set_ylabel(copy["y_label"], fontsize=11)
    ax.yaxis.set_major_formatter(lambda value, _pos: _money_vnd(value))
    ax.grid(True, color="#d9e2ec", linewidth=0.8, alpha=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", frameon=False)
    ax.text(
        0.5,
        0.02,
        copy["watermark"],
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=9,
        color="#627d98",
        alpha=0.9,
    )

    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
