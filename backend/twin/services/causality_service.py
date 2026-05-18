from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.event import Event
from backend.models.twin_projection import TwinProjection
from backend.twin.services.twin_projection_service import SCENARIO_CURRENT
from infra.cache import causality_cache

_CONTENT_PATH = Path(__file__).resolve().parents[3] / "content" / "twin" / "causality_explainer.yaml"
ZERO_DELTA_PCT = Decimal("0.10")


@dataclass(frozen=True, slots=True)
class CausalityFactor:
    factor: str
    contribution_pct: Decimal
    action_taken_at: datetime | None
    factor_type: str


@dataclass(frozen=True, slots=True)
class CausalityBreakdown:
    direction: str
    delta_pct: Decimal
    delta_absolute_vnd: Decimal
    factors: tuple[CausalityFactor, ...]
    text: str
    forward_sentence: str | None
    show_breakdown: bool


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _p50_at_horizon(projection: TwinProjection) -> Decimal:
    cone = projection.cone_data or []
    if not cone:
        return Decimal("0")
    point = cone[-1]
    return Decimal(str(point.get("p50", 0)))


def _format_vnd(amount: Decimal) -> str:
    amount = abs(amount)
    if amount >= Decimal("1000000000"):
        return f"{(amount / Decimal('1000000000')).quantize(Decimal('0.1'))} tỷ"
    if amount >= Decimal("1000000"):
        return f"{(amount / Decimal('1000000')).quantize(Decimal('1'))}tr"
    return f"{amount:,.0f}đ"


def build_weighted_factors(raw: Iterable[dict[str, Any]], *, max_items: int = 5) -> tuple[CausalityFactor, ...]:
    weighted: list[tuple[dict[str, Any], Decimal]] = []
    for item in raw:
        weight = abs(Decimal(str(item.get("delta_absolute_vnd") or item.get("amount") or 0)))
        if weight > 0:
            weighted.append((item, weight))
    total = sum((w for _, w in weighted), Decimal("0"))
    if total <= 0:
        return ()
    weighted.sort(key=lambda pair: pair[1], reverse=True)
    selected = weighted[:max_items]
    remaining = weighted[max_items:]
    factors = [
        CausalityFactor(
            factor=str(item.get("label") or item.get("factor") or _label_for_event(str(item.get("event_type", "update")), weight)),
            contribution_pct=(weight / total * Decimal("100")).quantize(Decimal("0.1")),
            action_taken_at=item.get("action_taken_at"),
            factor_type=str(item.get("factor_type") or item.get("event_type") or "other"),
        )
        for item, weight in selected
    ]
    if remaining:
        other_weight = sum((w for _, w in remaining), Decimal("0"))
        factors.append(
            CausalityFactor(
                factor=_copy().get("other_label", "Khác"),
                contribution_pct=(other_weight / total * Decimal("100")).quantize(Decimal("0.1")),
                action_taken_at=None,
                factor_type="other",
            )
        )
    if factors:
        drift = Decimal("100.0") - sum(f.contribution_pct for f in factors)
        last = factors[-1]
        factors[-1] = CausalityFactor(
            factor=last.factor,
            contribution_pct=last.contribution_pct + drift,
            action_taken_at=last.action_taken_at,
            factor_type=last.factor_type,
        )
    return tuple(factors)


def _label_for_event(event_type: str, amount: Decimal) -> str:
    if event_type.startswith("asset"):
        return f"Anh cập nhật tài sản {_format_vnd(amount)}"
    if event_type.startswith("income"):
        return f"Anh ghi nhận thu nhập {_format_vnd(amount)}"
    if event_type.startswith("expense"):
        return f"Anh ghi nhận chi tiêu {_format_vnd(amount)}"
    if event_type.startswith("goal"):
        return "Anh chạm một mốc mục tiêu"
    return "Cập nhật tài chính mới"


def _render(direction: str, factors: tuple[CausalityFactor, ...], forward: str | None) -> str:
    copy = _copy()
    if not factors:
        return copy.get("zero_delta", "Twin của anh ổn định tuần này")
    if direction == "negative":
        lines = ["Vì sao Twin nhích xuống?", f"• Điểm chính: {factors[0].factor}"]
    else:
        headline = copy["headline"].get(direction, copy["headline"]["positive"])[0]
        lines = [headline]
        lines.extend(f"✓ {f.factor} ({f.contribution_pct}%)" for f in factors)
    if forward:
        lines.extend(["", f"💡 {forward}"])
    return "\n".join(lines)


def _forward_sentence(current: Decimal, delta: Decimal, target_year: int | None = None) -> str | None:
    if current <= 0 or delta == 0:
        return None
    target_year = target_year or (date.today().year + 4)
    annualized = delta * Decimal("52")
    projected = current + annualized * Decimal(max(target_year - date.today().year, 1))
    template = _copy()["forward"]["positive"][0] if delta > 0 else _copy()["forward"]["negative"][0]
    if delta < 0:
        return template
    return template.format(target_year=target_year, amount=_format_vnd(projected))


async def _recent_factor_events(db: AsyncSession, user_id: uuid.UUID, period_days: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
    result = await db.execute(
        select(Event)
        .where(Event.user_id == user_id, Event.timestamp >= cutoff)
        .where(Event.event_type.in_(["asset.created", "asset.updated", "income.added", "expense.added", "goal.milestone_reached"]))
        .order_by(desc(Event.timestamp))
        .limit(25)
    )
    rows = result.scalars().all()
    factors = []
    for row in rows:
        props = row.properties or {}
        amount = props.get("delta_absolute_vnd") or props.get("amount") or 0
        factors.append(
            {
                "event_type": row.event_type,
                "amount": amount,
                "delta_absolute_vnd": amount,
                "action_taken_at": row.timestamp,
                "factor_type": row.event_type.split(".")[0],
                "label": props.get("label"),
            }
        )
    return factors


async def attribute_delta(db: AsyncSession, user_id: uuid.UUID, period_days: int = 7) -> CausalityBreakdown:
    cache_key = f"causality:{user_id}:{date.today().isoformat()}:{period_days}"
    cached = causality_cache.get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(TwinProjection)
        .where(TwinProjection.user_id == user_id, TwinProjection.scenario == SCENARIO_CURRENT)
        .order_by(desc(TwinProjection.computed_at))
        .limit(10)
    )
    projections = result.scalars().all()
    if len(projections) < 2:
        current = _p50_at_horizon(projections[0]) if projections else Decimal("0")
        delta = Decimal("0")
    else:
        current = _p50_at_horizon(projections[0])
        previous = _p50_at_horizon(projections[-1])
        delta = current - previous
    delta_pct = Decimal("0") if current == 0 else (delta / current * Decimal("100")).quantize(Decimal("0.01"))
    direction = "positive" if delta > 0 else "negative" if delta < 0 else "stable"
    if abs(delta_pct) < ZERO_DELTA_PCT:
        breakdown = CausalityBreakdown(direction="stable", delta_pct=delta_pct, delta_absolute_vnd=delta, factors=(), text=_copy().get("zero_delta"), forward_sentence=None, show_breakdown=False)
        causality_cache.set(cache_key, breakdown)
        return breakdown

    raw = await _recent_factor_events(db, user_id, period_days)
    if not raw:
        raw = [{"label": "Các cập nhật tài chính trong tuần", "delta_absolute_vnd": abs(delta), "factor_type": "twin"}]
    factors = build_weighted_factors(raw, max_items=5)
    if direction == "negative" and factors:
        factors = (factors[0],)
    forward = _forward_sentence(current, delta)
    breakdown = CausalityBreakdown(direction=direction, delta_pct=delta_pct, delta_absolute_vnd=delta, factors=factors, text=_render(direction, factors, forward), forward_sentence=forward, show_breakdown=True)
    causality_cache.set(cache_key, breakdown)
    return breakdown


def breakdown_to_dict(breakdown: CausalityBreakdown) -> dict[str, Any]:
    data = asdict(breakdown)
    data["delta_pct"] = str(breakdown.delta_pct)
    data["delta_absolute_vnd"] = str(breakdown.delta_absolute_vnd)
    data["factors"] = [
        {**asdict(f), "contribution_pct": str(f.contribution_pct), "action_taken_at": f.action_taken_at.isoformat() if f.action_taken_at else None}
        for f in breakdown.factors
    ]
    return data
