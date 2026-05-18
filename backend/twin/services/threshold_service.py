from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.twin_habit_loop import TwinDeltaThresholdConfig


@dataclass(frozen=True, slots=True)
class ThresholdConfig:
    wealth_segment: str
    positive_pct: Decimal
    positive_absolute_vnd: Decimal
    negative_pct: Decimal
    negative_absolute_vnd: Decimal
    # Per-segment recompute trigger: an expense below this is silent — Twin
    # does not recompute. Distinct from notification thresholds (above), which
    # gate whether we tell the user about a recomputed delta.
    expense_recompute_trigger_vnd: Decimal = Decimal("100000")


DEFAULT_THRESHOLDS: dict[str, ThresholdConfig] = {
    "starter": ThresholdConfig(
        "starter", Decimal("1.0"), Decimal("1000000"), Decimal("1.0"), Decimal("1000000"),
        expense_recompute_trigger_vnd=Decimal("100000"),
    ),
    "young_pro": ThresholdConfig(
        "young_pro", Decimal("1.0"), Decimal("3000000"), Decimal("1.0"), Decimal("3000000"),
        expense_recompute_trigger_vnd=Decimal("500000"),
    ),
    "mass_affluent": ThresholdConfig(
        "mass_affluent", Decimal("1.0"), Decimal("10000000"), Decimal("1.0"), Decimal("10000000"),
        expense_recompute_trigger_vnd=Decimal("2000000"),
    ),
    "hnw": ThresholdConfig(
        "hnw", Decimal("0.5"), Decimal("50000000"), Decimal("0.5"), Decimal("50000000"),
        expense_recompute_trigger_vnd=Decimal("10000000"),
    ),
}


def normalize_segment(segment: str | None) -> str:
    if not segment:
        return "mass_affluent"
    return segment if segment in DEFAULT_THRESHOLDS else "mass_affluent"


def is_noticeable(
    user_segment: str | None,
    delta_pct: Decimal | int | float,
    delta_absolute_vnd: Decimal | int | float,
    *,
    config: ThresholdConfig | None = None,
) -> bool:
    """Return true when pct OR absolute delta reaches the inclusive segment threshold."""
    segment = normalize_segment(user_segment)
    cfg = config or DEFAULT_THRESHOLDS[segment]
    pct = abs(Decimal(str(delta_pct)))
    absolute = abs(Decimal(str(delta_absolute_vnd)))
    is_negative = Decimal(str(delta_absolute_vnd)) < 0 or Decimal(str(delta_pct)) < 0
    pct_threshold = cfg.negative_pct if is_negative else cfg.positive_pct
    absolute_threshold = cfg.negative_absolute_vnd if is_negative else cfg.positive_absolute_vnd
    return pct >= pct_threshold or absolute >= absolute_threshold


async def get_threshold_config(db: AsyncSession, segment: str | None) -> ThresholdConfig:
    normalized = normalize_segment(segment)
    result = await db.execute(
        select(TwinDeltaThresholdConfig).where(
            TwinDeltaThresholdConfig.wealth_segment == normalized
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return DEFAULT_THRESHOLDS[normalized]
    return ThresholdConfig(
        wealth_segment=row.wealth_segment,
        positive_pct=row.positive_threshold_pct,
        positive_absolute_vnd=row.positive_threshold_absolute_vnd,
        negative_pct=row.negative_threshold_pct,
        negative_absolute_vnd=row.negative_threshold_absolute_vnd,
        expense_recompute_trigger_vnd=row.expense_recompute_trigger_vnd,
    )


def should_recompute_for_expense(
    user_segment: str | None,
    expense_amount_vnd: Decimal | int | float,
    *,
    config: ThresholdConfig | None = None,
) -> bool:
    """Whether an expense is large enough to trigger Twin recompute.

    Inclusive (``>=``) so a Starter spending exactly 100k still triggers.
    HNW spending under 10tr is silently absorbed — recomputing Twin for a
    50k coffee on a multi-tỷ portfolio is noise.
    """
    segment = normalize_segment(user_segment)
    cfg = config or DEFAULT_THRESHOLDS[segment]
    return abs(Decimal(str(expense_amount_vnd))) >= cfg.expense_recompute_trigger_vnd


async def tune_threshold(
    db: AsyncSession,
    segment: str,
    pct: Decimal | int | float,
    absolute_vnd: Decimal | int | float,
    *,
    updated_by: str = "operator",
    negative_pct: Decimal | int | float | None = None,
    negative_absolute_vnd: Decimal | int | float | None = None,
) -> ThresholdConfig:
    normalized = normalize_segment(segment)
    cfg = await db.get(TwinDeltaThresholdConfig, normalized)
    if cfg is None:
        cfg = TwinDeltaThresholdConfig(wealth_segment=normalized)
        db.add(cfg)
    cfg.positive_threshold_pct = Decimal(str(pct))
    cfg.positive_threshold_absolute_vnd = Decimal(str(absolute_vnd))
    cfg.negative_threshold_pct = Decimal(str(negative_pct if negative_pct is not None else pct))
    cfg.negative_threshold_absolute_vnd = Decimal(str(negative_absolute_vnd if negative_absolute_vnd is not None else absolute_vnd))
    cfg.updated_by = updated_by
    await db.flush()
    return ThresholdConfig(
        normalized,
        cfg.positive_threshold_pct,
        cfg.positive_threshold_absolute_vnd,
        cfg.negative_threshold_pct,
        cfg.negative_threshold_absolute_vnd,
        expense_recompute_trigger_vnd=cfg.expense_recompute_trigger_vnd,
    )


def histogram_overlay_config() -> Mapping[str, ThresholdConfig]:
    """Small read model for the Epic 4 dashboard histogram overlay."""
    return DEFAULT_THRESHOLDS
