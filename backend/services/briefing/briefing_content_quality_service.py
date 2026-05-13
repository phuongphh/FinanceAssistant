"""First briefing content-quality guardrail (Phase 4.2 Epic 2).

Template-based by design: fast, deterministic, and budget-safe. If future LLM
personalization is added, it must call through the Phase 4.1 cost adapter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.onboarding_session import (
    GOAL_TRACK_SPENDING,
    SEGMENT_HNW,
    SEGMENT_MASS_AFFLUENT,
    SEGMENT_STARTER,
    SEGMENT_YOUNG_PRO,
    OnboardingSession,
)
from backend.wealth.models.asset import Asset

_CONTENT_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "briefing"
    / "content_quality_templates.yaml"
)


@dataclass(frozen=True)
class BriefingInsight:
    template_key: str
    insight_text: str
    suggested_query: str

    @property
    def render_text(self) -> str:
        return (
            f"🔎 {self.insight_text}\n💬 Hỏi thử: <code>{self.suggested_query}</code>"
        )


def load_templates() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


async def _asset_state(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[list[Asset], Decimal, dict[str, Decimal]]:
    result = await db.execute(
        select(Asset).where(
            Asset.user_id == user_id,
            Asset.is_active.is_(True),
            Asset.is_placeholder_asset.is_(False),
            Asset.is_confirmed.is_(True),
        )
    )
    assets = list(result.scalars().all())
    by_type: dict[str, Decimal] = {}
    total = Decimal("0")
    for asset in assets:
        value = Decimal(asset.current_value or 0)
        if value <= 0:
            continue
        total += value
        by_type[asset.asset_type] = by_type.get(asset.asset_type, Decimal("0")) + value
    return assets, total, by_type


async def _expense_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(func.count(Expense.id)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
    )
    return int((await db.execute(stmt)).scalar() or 0)


def _top_asset_label(by_type: dict[str, Decimal]) -> str:
    if not by_type:
        return "một nhóm tài sản"
    return max(by_type.items(), key=lambda item: item[1])[0]


def _from_template(copy: dict[str, Any], key: str, **fmt: Any) -> BriefingInsight:
    item = copy["templates"][key]
    return BriefingInsight(
        template_key=key,
        insight_text=item["insight_text"].format(**fmt),
        suggested_query=item["suggested_query"],
    )


async def compute_insight(db: AsyncSession, user_id: uuid.UUID) -> BriefingInsight:
    """Return at least one personalized insight for briefing #1."""
    copy = load_templates()
    session = await db.get(OnboardingSession, user_id)
    goal = session.goal_choice if session else None
    segment = session.inferred_wealth_segment if session else None
    assets, total, by_type = await _asset_state(db, user_id)
    asset_class_count = len(by_type)
    cash_ratio = (
        (by_type.get("cash", Decimal("0")) / total * Decimal("100"))
        if total > 0
        else Decimal("0")
    )

    if goal == GOAL_TRACK_SPENDING and await _expense_count(db, user_id) == 0:
        return _from_template(copy, "track_spending_no_logs")
    if segment == SEGMENT_HNW:
        return _from_template(copy, "hnw_portfolio")
    if segment == SEGMENT_MASS_AFFLUENT and asset_class_count == 1:
        return _from_template(
            copy, "mass_affluent_single_class", top_asset=_top_asset_label(by_type)
        )
    if segment == SEGMENT_YOUNG_PRO and assets and cash_ratio == Decimal("100"):
        return _from_template(copy, "young_pro_cash_only")
    if segment == SEGMENT_STARTER:
        return _from_template(copy, "starter_first_asset")

    fallback = copy["fallback"]
    return BriefingInsight(
        template_key="fallback",
        insight_text=fallback["insight_text"],
        suggested_query=fallback["suggested_query"],
    )
