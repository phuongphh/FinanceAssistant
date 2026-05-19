"""Channel-agnostic read model for Financial Twin Mini App/API.

Routes own authentication and HTTP caching. This module owns only the stable
JSON shape so Telegram WebApp today and future Zalo surfaces can reuse it.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.life_events import service as life_event_service
from backend.life_events.impact import (
    adjust_cone_with_events,
    base_year_from_computed_at,
)
from backend.models.user import User
from backend.twin import label_resolver
from backend.twin.engine.uncertainty import compute_uncertainty_breakdown
from backend.twin.services import (
    life_outcome_translator,
    twin_projection_service,
    twin_query_service,
)
from backend.twin.services.growth_rate_calculator import calculate_growth_snapshot
from backend.twin.views.present_anchor import (
    build_present_anchor_view,
    present_anchor_to_payload,
)
from backend.twin.views.scenario_card import scenario_cards_for_point
from backend.twin.flows.first_time_view import build_story_flow, should_show_full_story

_ALLOWED_SCENARIOS = {
    twin_projection_service.SCENARIO_CURRENT,
    twin_projection_service.SCENARIO_OPTIMAL,
}
_EMPTY_COPY = (
    "Twin cần tối thiểu 10tr tài sản đã ghi nhận để mô phỏng có ý nghĩa. "
    "Thêm/cập nhật tài sản rồi quay lại nhé."
)
_MILESTONE_CALENDAR_YEARS = (2027, 2030, 2035)
_SAVINGS_ROUND = Decimal("500000")
_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "twin_copy.yaml"


@lru_cache(maxsize=1)
def _scenario_comparison_copy() -> dict[str, str]:
    """Return the ``scenario_comparison`` block from twin_copy.yaml."""
    with _COPY_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data.get("scenario_comparison") or {})


async def build_twin_payload(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    scenario: str = twin_projection_service.SCENARIO_CURRENT,
    exclude_event_ids: set[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Return the latest Twin projection payload for a user.

    This is intentionally read-only: no Monte Carlo recompute inside the GET
    path, preserving the Phase 4A "weekly heavy, daily light" performance
    principle. If no projection exists, callers still receive an authenticated
    empty-state payload rather than an exception.
    """
    if scenario not in _ALLOWED_SCENARIOS:
        raise ValueError(f"Unsupported Twin scenario: {scenario}")

    snapshot = await twin_query_service.get_twin_snapshot(db, user_id)
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    show_technical_terms = bool(getattr(user, "twin_show_technical_terms", False))
    labels = label_resolver.labels_for_payload(
        show_technical_terms=show_technical_terms
    )
    projection = await twin_query_service.get_latest_projection(
        db, user_id, scenario=scenario
    )

    # Fire-and-forget background recompute when the stored cone no longer
    # matches the wallet. The GET path stays read-only — we do not block
    # the response — but the next view shows the fresh cone. Failure here
    # is swallowed because the stale cone is still useful with a banner.
    if snapshot.is_value_stale and snapshot.actual_nw > 0:
        try:
            from backend.twin.services import recompute_service

            delta_for_signal = (
                snapshot.actual_nw - Decimal(str(projection.base_net_worth or 0))
                if projection
                else snapshot.actual_nw
            )
            await recompute_service.enqueue_recompute_if_needed(
                db, user_id, delta_for_signal
            )
        except Exception:
            # Never let recompute scheduling break the read path.
            pass

    if projection is None:
        return {
            "has_projection": False,
            "scenario": scenario,
            "base_net_worth": _money(snapshot.actual_nw),
            "actual_net_worth": _money(snapshot.actual_nw),
            "delta_vs_p50": None,
            "allocation": {},
            "cone": [],
            "computed_at": None,
            "cone_age_days": snapshot.cone_age_days,
            "is_stale": True,
            "is_value_stale": True,
            "engine_version": twin_projection_service.DEFAULT_ENGINE_VERSION,
            "empty_state": _EMPTY_COPY,
            "scenario_labels": labels,
            "show_technical_terms": show_technical_terms,
            "story_flow": {"mode": "empty", "screens": []},
        }

    # For comparison deltas: always load both scenarios regardless of view scenario
    current_proj = await twin_query_service.get_latest_projection(
        db, user_id, scenario=twin_projection_service.SCENARIO_CURRENT
    )
    optimal_proj = await twin_query_service.get_latest_projection(
        db, user_id, scenario=twin_projection_service.SCENARIO_OPTIMAL
    )
    comparison_deltas = _compute_comparison_deltas(
        current_proj, optimal_proj, projection.computed_at
    )
    monthly_savings_needed = _compute_monthly_savings_needed(current_proj, optimal_proj)
    optimal_strategy = _derive_optimal_strategy(current_proj, optimal_proj)

    # Phase 4B Epic 2: ``exclude_event_ids`` lets the Mini App toggle a single
    # event off and re-render the cone WITHOUT a Monte Carlo recompute. We
    # start from ``base_cone_data`` (no events applied) and re-add the deltas
    # of the events the caller still wants — strictly arithmetic on the cone.
    cone_payload = projection.cone_data or []
    excluded_count = 0
    if exclude_event_ids and projection.base_cone_data:
        remaining_events = [
            ev
            for ev in await life_event_service.list_for_user(db, user_id)
            if ev.id not in exclude_event_ids
        ]
        base_year = base_year_from_computed_at(projection.computed_at)
        cone_payload = adjust_cone_with_events(
            projection.base_cone_data, remaining_events, base_year
        )
        excluded_count = len(exclude_event_ids)

    target_point = _target_point(cone_payload)
    target_year = _calendar_year(
        projection.computed_at, int(target_point.get("year", 0))
    )
    target_p50 = Decimal(str(target_point.get("p50") or 0))
    growth = await calculate_growth_snapshot(
        db, user_id, current_net_worth=snapshot.actual_nw
    )
    present_anchor = build_present_anchor_view(
        growth,
        target_year=target_year,
        target_p50=target_p50,
        breakdown=getattr(snapshot, "actual_breakdown", {}) or {},
    )
    outcome_context = {
        "location": "TP.HCM",
        "known_goals": (
            [getattr(user, "primary_goal", None)]
            if getattr(user, "primary_goal", None)
            else []
        ),
        "user_segment": getattr(user, "wealth_level", None) or "mass_affluent",
    }
    life_outcome = await life_outcome_translator.translate(
        db,
        amount_vnd=target_p50,
        target_year=target_year,
        user_context=outcome_context,
    )
    scenario_cards = scenario_cards_for_point(target_point, labels)

    payload = {
        "has_projection": True,
        "scenario": projection.scenario,
        "base_net_worth": _money(projection.base_net_worth),
        "actual_net_worth": _money(snapshot.actual_nw),
        "delta_vs_p50": (
            _money(snapshot.delta_vs_p50) if snapshot.delta_vs_p50 is not None else None
        ),
        "monthly_savings": _money(projection.monthly_savings),
        "allocation": _allocation_to_json(projection.allocation_snapshot or {}),
        "cone": _cone_to_json(cone_payload),
        "scenario_labels": labels,
        "show_technical_terms": show_technical_terms,
        "present_anchor": present_anchor_to_payload(present_anchor),
        "life_outcome": life_outcome,
        "computed_at": _isoformat(projection.computed_at),
        "cone_age_days": snapshot.cone_age_days,
        "is_stale": snapshot.is_stale,
        "is_value_stale": snapshot.is_value_stale,
        "horizon_years": projection.horizon_years,
        "sim_paths": projection.sim_paths,
        "engine_version": projection.engine_version,
        "comparison_deltas": comparison_deltas,
        "optimal_strategy": optimal_strategy,
        "scenario_comparison_copy": _strategy_copy(optimal_strategy),
        "monthly_savings_needed": (
            _money(monthly_savings_needed)
            if monthly_savings_needed is not None
            else None
        ),
        "uncertainty_contributors": _uncertainty_to_json(
            projection.allocation_snapshot or {}
        ),
        "scenario_cards": scenario_cards,
        "excluded_event_count": excluded_count,
    }
    payload["story_flow"] = build_story_flow(
        payload, full_flow=await should_show_full_story(db, user_id)
    )
    return payload


def _target_point(cone: list[dict[str, Any]]) -> dict[str, Any]:
    if not cone:
        return {"year": 0, "p50": 0}
    return max(cone, key=lambda point: int(point.get("year", 0)))


def _calendar_year(computed_at: datetime | None, year_offset: int) -> int:
    base = computed_at or datetime.now(timezone.utc)
    return int(base.year) + int(year_offset)


def etag_for_payload(payload: dict[str, Any]) -> str:
    """Stable weak ETag for Twin responses.

    Computed from fields that change whenever a new projection snapshot becomes
    visible. Empty-state ETags also vary by current net worth so add-asset flows
    are not stuck behind a stale 304. ``excluded_event_count`` is folded in so
    toggling life events on/off invalidates the cache predictably.
    """
    basis = "|".join(
        str(payload.get(key) or "")
        for key in (
            "scenario",
            "computed_at",
            "actual_net_worth",
            "base_net_worth",
            "engine_version",
            "excluded_event_count",
            "is_value_stale",
            "optimal_strategy",
            "story_flow",
        )
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return f'W/"twin-{digest}"'


def _money(value: Decimal | int | float | str | None) -> str:
    if value is None:
        return "0"
    return str(Decimal(str(value)).quantize(Decimal("1")))


def _allocation_to_json(allocation: dict[str, Any]) -> dict[str, float]:
    return {key: float(Decimal(str(value))) for key, value in allocation.items()}


def _cone_to_json(cone: list[dict[str, Any]]) -> list[dict[str, int | str]]:
    return [
        {
            "year": int(point.get("year", 0)),
            "p10": _money(point.get("p10")),
            "p50": _money(point.get("p50")),
            "p90": _money(point.get("p90")),
        }
        for point in cone
    ]


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _compute_comparison_deltas(
    current_proj: Any,
    optimal_proj: Any,
    computed_at: datetime,
) -> list[dict[str, Any]]:
    """Return delta % at milestone years (2027, 2030, 2035) between optimal and current."""
    if current_proj is None or optimal_proj is None:
        return []

    base_year = computed_at.year if computed_at else datetime.now(timezone.utc).year
    current_by_idx = {int(p.get("year", -1)): p for p in (current_proj.cone_data or [])}
    optimal_by_idx = {int(p.get("year", -1)): p for p in (optimal_proj.cone_data or [])}

    deltas = []
    for cal_year in _MILESTONE_CALENDAR_YEARS:
        idx = cal_year - base_year
        if idx < 0 or idx > (current_proj.horizon_years or 10):
            continue
        cur_point = current_by_idx.get(idx)
        opt_point = optimal_by_idx.get(idx)
        if cur_point is None or opt_point is None:
            continue
        cur_p50 = Decimal(str(cur_point.get("p50") or 0))
        opt_p50 = Decimal(str(opt_point.get("p50") or 0))
        if cur_p50 <= 0:
            continue
        delta_pct = (opt_p50 - cur_p50) / cur_p50 * Decimal("100")
        deltas.append(
            {
                "year": cal_year,
                "current_p50": _money(cur_p50),
                "optimal_p50": _money(opt_p50),
                "delta_pct": float(delta_pct.quantize(Decimal("0.1"))),
            }
        )
    return deltas


def _uncertainty_to_json(allocation: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        contributors = compute_uncertainty_breakdown(allocation, top_n=2)
    except Exception:
        return []
    return [
        {"asset_class": c.asset_class, "contribution_pct": c.contribution_pct}
        for c in contributors
    ]


def _compute_monthly_savings_needed(
    current_proj: Any,
    optimal_proj: Any,
) -> Decimal | None:
    """Return (optimal_savings - current_savings) rounded to nearest 500k, or None."""
    if current_proj is None or optimal_proj is None:
        return None
    cur_savings = Decimal(str(current_proj.monthly_savings or 0))
    opt_savings = Decimal(str(optimal_proj.monthly_savings or 0))
    diff = opt_savings - cur_savings
    if diff <= 0:
        return None
    # Round to nearest 500k
    rounded = (diff / _SAVINGS_ROUND).quantize(Decimal("1")) * _SAVINGS_ROUND
    return max(rounded, Decimal("0"))


_ALLOCATION_MATCH_TOLERANCE = Decimal("0.005")


def _strategy_copy(strategy: str | None) -> dict[str, str]:
    """Return the localized copy bundle for ``strategy`` (defaults to rebalance)."""
    copy = _scenario_comparison_copy()
    tooltip_key = (
        "tooltip_optimal_savings_only"
        if strategy == "savings_only"
        else "tooltip_optimal_rebalance"
    )
    cta_key = "cta_savings_only" if strategy == "savings_only" else "cta_savings"
    return {
        "tooltip": str(copy.get(tooltip_key) or copy.get("tooltip_optimal") or ""),
        "cta_savings": str(copy.get(cta_key) or copy.get("cta_savings") or ""),
        "cta_no_change": str(copy.get("cta_no_change") or ""),
    }


def _derive_optimal_strategy(current_proj: Any, optimal_proj: Any) -> str | None:
    """Return ``"savings_only"`` when optimal keeps current weights, else ``"rebalance_to_target"``.

    The Pareto-aware engine swaps in the user's current allocation when the
    wealth-tier target would lower expected return; comparing the two stored
    snapshots avoids a schema migration to persist the decision explicitly.
    """
    if current_proj is None or optimal_proj is None:
        return None
    current_alloc = current_proj.allocation_snapshot or {}
    optimal_alloc = optimal_proj.allocation_snapshot or {}
    if not current_alloc or not optimal_alloc:
        return None
    assets = set(current_alloc) | set(optimal_alloc)
    for asset in assets:
        cur = Decimal(str(current_alloc.get(asset, 0)))
        opt = Decimal(str(optimal_alloc.get(asset, 0)))
        if abs(cur - opt) > _ALLOCATION_MATCH_TOLERANCE:
            return "rebalance_to_target"
    return "savings_only"
