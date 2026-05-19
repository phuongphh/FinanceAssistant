"""Presentation helpers for the Phase 4.3 Twin present anchor."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from backend.bot.formatters.money import format_money_short
from backend.twin.services.growth_rate_calculator import (
    GrowthRateSnapshot,
    is_small_delta,
)


@dataclass(frozen=True, slots=True)
class PresentAnchorView:
    present_label: str
    weekly_delta_label: str
    growth_rate_label: str
    projected_if_maintained_label: str | None
    tone: str
    breakdown: dict[str, str] = field(default_factory=dict)
    volatility_review_required: bool = False


def build_present_anchor_view(
    growth: GrowthRateSnapshot,
    *,
    target_year: int | None = None,
    target_p50: Decimal | None = None,
    breakdown: dict[str, Decimal] | None = None,
) -> PresentAnchorView:
    current = Decimal(growth.current_net_worth or 0)
    if current < 0:
        present = f"Hiện tại: -{format_money_short(abs(current))}"
        tone = "amber"
    else:
        present = f"Hiện tại: {format_money_short(current)}"
        tone = "neutral"

    delta_label = _weekly_delta_label(growth.weekly_delta)
    if growth.weekly_delta and growth.weekly_delta > 0:
        tone = "positive"
    elif growth.weekly_delta and growth.weekly_delta < 0:
        tone = "amber"

    if growth.has_enough_data and growth.monthly_growth_rate is not None:
        rate_abs = abs(growth.monthly_growth_rate)
        prefix = "Tốc độ ~ " if growth.monthly_growth_rate >= 0 else "Tốc độ ~ -"
        growth_label = f"{prefix}{format_money_short(rate_abs)}/tháng"
    else:
        growth_label = "Đang theo dõi nhịp"

    maintained = None
    if target_year is not None and target_p50 is not None:
        maintained = f"Nếu duy trì, năm {target_year} có thể đạt ⛅ {format_money_short(target_p50)}"

    rendered_breakdown = {
        key: format_money_short(Decimal(value or 0))
        for key, value in (breakdown or {}).items()
    }
    return PresentAnchorView(
        present_label=present,
        weekly_delta_label=delta_label,
        growth_rate_label=growth_label,
        projected_if_maintained_label=maintained,
        tone=tone,
        breakdown=rendered_breakdown,
        volatility_review_required=growth.volatility_review_required,
    )


def _weekly_delta_label(delta: Decimal | None) -> str:
    if is_small_delta(delta):
        return "Ổn định"
    value = Decimal(delta or 0)
    arrow = "↑" if value > 0 else "↓"
    verb = "Tăng" if value > 0 else "Giảm"
    return f"{arrow} {verb} {format_money_short(abs(value))}"


def present_anchor_to_payload(view: PresentAnchorView) -> dict[str, Any]:
    return {
        "present_label": view.present_label,
        "weekly_delta_label": view.weekly_delta_label,
        "growth_rate_label": view.growth_rate_label,
        "projected_if_maintained_label": view.projected_if_maintained_label,
        "tone": view.tone,
        "breakdown": view.breakdown,
        "volatility_review_required": view.volatility_review_required,
    }
