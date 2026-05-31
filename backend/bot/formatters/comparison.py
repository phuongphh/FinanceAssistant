"""Shared "A vs B" comparison block — the ``⚖️ So sánh …`` layout.

Two surfaces render this exact block and MUST stay byte-identical:
- the Tier2 agent's free-form ``compare_periods`` answers
  (e.g. "So sánh tài sản của tôi so với tháng trước"), and
- the asset-list follow-up buttons ("📈 So với tháng trước" / "📈 YTD")
  which re-route to ``query_net_worth``.

Keeping the format here (instead of inline in each caller) is why a tap
and the typed question produce the same message.

Metric labels are Vietnamese — never surface the raw English metric key
(``net_worth``) to the user. ``net_worth`` maps to "Tổng tài sản" to match
the briefing / asset surfaces (see ``content/briefing*.yaml``).
"""

from __future__ import annotations

from decimal import Decimal

from backend.bot.formatters.money import format_money_short

# Vietnamese labels for the comparable metrics. Mirrors the metric values
# in ``backend.agent.tools.schemas.CompareMetric`` so both the agent tool
# and the intent follow-up buttons translate consistently.
METRIC_LABELS_VI: dict[str, str] = {
    "net_worth": "Tổng tài sản",
    "expenses": "Chi tiêu",
    "income": "Thu nhập",
    "savings": "Tiết kiệm",
}


def metric_label_vi(metric: str) -> str:
    """Vietnamese label for a comparable metric, falling back to the key."""
    return METRIC_LABELS_VI.get(metric, metric)


def format_comparison_block(
    *,
    metric_label: str,
    label_a: str,
    value_a: float | Decimal,
    label_b: str,
    value_b: float | Decimal,
    diff: float | Decimal,
    diff_pct: float,
) -> str:
    """Render the shared ``⚖️ So sánh …`` block.

    ``label_a`` / ``label_b`` are rendered verbatim — callers pass them
    already cased (e.g. "Tháng này"). ``diff`` is ``value_a - value_b``;
    a non-negative diff reads as a gain (📈), negative as a loss (📉).
    """
    sign = "+" if diff >= 0 else ""
    arrow = "📈" if diff > 0 else ("📉" if diff < 0 else "➡️")

    return (
        f"⚖️ So sánh {metric_label}:\n\n"
        f"• {label_a}: {format_money_short(value_a)}\n"
        f"• {label_b}: {format_money_short(value_b)}\n\n"
        f"{arrow} Chênh lệch: {sign}{format_money_short(diff)} "
        f"({sign}{diff_pct:.1f}%)"
    )


__all__ = ["METRIC_LABELS_VI", "format_comparison_block", "metric_label_vi"]
