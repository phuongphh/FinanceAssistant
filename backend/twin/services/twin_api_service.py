"""Channel-agnostic read model for Financial Twin Mini App/API.

Routes own authentication and HTTP caching. This module owns only the stable
JSON shape so Telegram WebApp today and future Zalo surfaces can reuse it.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.twin.services import twin_projection_service, twin_query_service

_ALLOWED_SCENARIOS = {
    twin_projection_service.SCENARIO_CURRENT,
    twin_projection_service.SCENARIO_OPTIMAL,
}
_EMPTY_COPY = (
    "Twin cần tối thiểu 10tr tài sản đã ghi nhận để mô phỏng có ý nghĩa. "
    "Thêm/cập nhật tài sản rồi quay lại nhé."
)


async def build_twin_payload(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    scenario: str = twin_projection_service.SCENARIO_CURRENT,
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
    projection = await twin_query_service.get_latest_projection(
        db, user_id, scenario=scenario
    )
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
            "engine_version": twin_projection_service.DEFAULT_ENGINE_VERSION,
            "empty_state": _EMPTY_COPY,
        }

    return {
        "has_projection": True,
        "scenario": projection.scenario,
        "base_net_worth": _money(projection.base_net_worth),
        "actual_net_worth": _money(snapshot.actual_nw),
        "delta_vs_p50": _money(snapshot.delta_vs_p50)
        if snapshot.delta_vs_p50 is not None
        else None,
        "monthly_savings": _money(projection.monthly_savings),
        "allocation": _allocation_to_json(projection.allocation_snapshot or {}),
        "cone": _cone_to_json(projection.cone_data or []),
        "computed_at": _isoformat(projection.computed_at),
        "cone_age_days": snapshot.cone_age_days,
        "is_stale": snapshot.is_stale,
        "horizon_years": projection.horizon_years,
        "sim_paths": projection.sim_paths,
        "engine_version": projection.engine_version,
    }


def etag_for_payload(payload: dict[str, Any]) -> str:
    """Stable weak ETag for Twin responses.

    Computed from fields that change whenever a new projection snapshot becomes
    visible. Empty-state ETags also vary by current net worth so add-asset flows
    are not stuck behind a stale 304.
    """
    basis = "|".join(
        str(payload.get(key) or "")
        for key in ("scenario", "computed_at", "actual_net_worth", "engine_version")
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
