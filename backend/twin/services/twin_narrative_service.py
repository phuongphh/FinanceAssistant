"""Short Financial Twin narrative generation with conservative fallback."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
from backend.models.user import User
from backend.services.llm_service import LLMError, call_llm
from backend.wealth.ladder import detect_level
from backend.wealth.models.asset import Asset
from backend.wealth.models.asset_snapshot import AssetSnapshot
from backend.wealth.services import net_worth_calculator as wealth_service

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "twin_copy.yaml"


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["narrative"]


def cone_hash(cone: list[dict[str, Any]]) -> str:
    payload = "|".join(
        f"{p.get('year')}:{p.get('p10')}:{p.get('p50')}:{p.get('p90')}" for p in cone
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _clean_output(text: str, fallback_p50: str, fallback_year: int) -> str:
    cleaned = " ".join(text.replace("*", "").replace("_", "").split())
    technical_terms = ("P10", "P50", "P90")
    if 50 <= len(cleaned) <= 200 and not any(
        term in cleaned.upper() for term in technical_terms
    ):
        return cleaned
    return _copy()["fallback"].format(target_year=fallback_year, p50=fallback_p50)


async def _get_top_asset_changes(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    days: int = 30,
    top_n: int = 2,
) -> str:
    """Return a compact string describing the top asset value changes over `days`."""
    today = date.today()
    cutoff = today - timedelta(days=days)

    stmt = select(Asset).where(Asset.user_id == user_id, Asset.is_active.is_(True))
    assets = list((await db.execute(stmt)).scalars().all())
    if not assets:
        return "không có thay đổi đáng kể"

    old_stmt = (
        select(AssetSnapshot.asset_id, AssetSnapshot.value)
        .where(
            AssetSnapshot.user_id == user_id,
            AssetSnapshot.snapshot_date >= cutoff,
            AssetSnapshot.snapshot_date <= cutoff + timedelta(days=3),
        )
        .order_by(AssetSnapshot.snapshot_date.asc())
    )
    old_rows = (await db.execute(old_stmt)).all()
    old_values: dict[uuid.UUID, Decimal] = {}
    for row in old_rows:
        if row.asset_id not in old_values:
            old_values[row.asset_id] = Decimal(str(row.value))

    changes: list[tuple[str, Decimal]] = []
    for asset in assets:
        current = Decimal(str(asset.current_value or 0))
        old = old_values.get(asset.id, current)
        delta = current - old
        if abs(delta) > 0:
            changes.append((asset.name or asset.asset_type, delta))

    if not changes:
        return "không có thay đổi đáng kể"

    changes.sort(key=lambda x: abs(x[1]), reverse=True)
    parts = []
    for name, delta in changes[:top_n]:
        sign = "+" if delta >= 0 else ""
        parts.append(f"{name} {sign}{format_money_short(delta)}")
    return ", ".join(parts)


async def build_twin_narrative(
    db: AsyncSession,
    user: User,
    cone: list[dict[str, Any]],
    *,
    cone_age_days: int | None,
) -> str:
    if not cone:
        return _copy()["fallback"].format(target_year="?", p50="?")
    target = cone[-1]
    target_year = target.get("year")
    p50_str = format_money_short(Decimal(str(target.get("p50", 0))))
    p10_str = format_money_short(Decimal(str(target.get("p10", 0))))
    p90_str = format_money_short(Decimal(str(target.get("p90", 0))))

    wealth_level_raw = getattr(user, "wealth_level", None)
    if wealth_level_raw:
        labels = _copy().get("wealth_level_labels", {})
        wealth_label = labels.get(wealth_level_raw, wealth_level_raw)
    else:
        try:
            breakdown = await wealth_service.calculate_stored_current(db, user.id)
            level = detect_level(breakdown.total)
            labels = _copy().get("wealth_level_labels", {})
            wealth_label = labels.get(level.value, level.value)
        except Exception:
            wealth_label = "chưa xác định"

    try:
        top_changes = await _get_top_asset_changes(db, user.id)
    except Exception:
        top_changes = "không có dữ liệu"

    # Phase 4B Epic 2: surface the user's planned life events to the LLM so
    # narratives can reference "mua nhà 2028" / "con đầu lòng 2030" instead
    # of the static "không có" placeholder from Phase 4A.
    try:
        from backend.life_events import service as life_event_service
        from backend.life_events.narrative import summary_for_twin_narrative

        events = await life_event_service.list_for_user(db, user.id)
        life_events_summary = summary_for_twin_narrative(events)
    except Exception:
        life_events_summary = "không có"

    prompt = _copy()["prompt"].format(
        target_year=target_year,
        p10=p10_str,
        p50=p50_str,
        p90=p90_str,
        cone_age_days=cone_age_days or 0,
        cone_hash=cone_hash(cone),
        wealth_level=wealth_label,
        top_changes=top_changes,
        life_events_summary=life_events_summary,
    )
    try:
        text = await call_llm(
            prompt,
            task_type="twin_narrative",
            db=db,
            user_id=user.id,
            use_cache=True,
            cache_ttl_days=7,
        )
        return _clean_output(text, p50_str, target_year)
    except (LLMError, Exception):
        return _copy()["fallback"].format(target_year=target_year, p50=p50_str)
