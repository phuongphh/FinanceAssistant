"""Admin dashboard endpoint for the Phase 3.7 agent system.

Aggregates ``agent_audit_logs`` into the slices the spec asks for:

- Today's totals: query count, cost, latency p95.
- Tier distribution (% Tier 1/2/3 today).
- Top 10 most expensive queries today.
- Top 10 slowest queries today.
- Top 10 unclear / failed queries today.
- 7-day cost trend (daily totals).

Auth: ``X-API-Key`` header matched against ``settings.internal_api_key``.
Same shape the rest of the admin surface uses (single key, single
operator). Multi-user admin surfaces wait for Phase 1+.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.models.agent_audit_log import AgentAuditLog

router = APIRouter(prefix="/admin/agent-metrics", tags=["admin"])


def _verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject calls without the configured admin key.

    Empty key in settings = endpoint locked entirely (returns 503),
    not "no auth required" — fail closed in case the operator forgot
    to set ``INTERNAL_API_KEY`` in prod."""
    expected = get_settings().internal_api_key
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="admin API not configured (INTERNAL_API_KEY unset)",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=403, detail="invalid X-API-Key")


def _today_start_utc() -> datetime:
    """UTC midnight today. Cheap dependency-free 'today' boundary."""
    return datetime.combine(date.today(), datetime.min.time())


@router.get("/today", dependencies=[Depends(_verify_api_key)])
async def today_summary(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Aggregate metrics for the calendar day so far (UTC).

    Returns the headline numbers a dashboard wants in one query
    burst — count, cost, p95 latency, tier distribution. p95 is
    computed via Postgres' ``percentile_cont`` so we don't need to
    pull every row over the wire."""
    since = _today_start_utc()

    # Headline totals.
    totals_stmt = select(
        func.count().label("count"),
        func.coalesce(func.sum(AgentAuditLog.cost_usd), 0).label("cost"),
        func.percentile_cont(0.95)
        .within_group(AgentAuditLog.total_latency_ms.asc())
        .label("p95_latency"),
        func.coalesce(
            func.sum(case((AgentAuditLog.success.is_(True), 1), else_=0)), 0
        ).label("success_count"),
    ).where(AgentAuditLog.query_timestamp >= since)
    row = (await db.execute(totals_stmt)).one()

    # Tier distribution.
    tier_stmt = (
        select(AgentAuditLog.tier_used, func.count())
        .where(AgentAuditLog.query_timestamp >= since)
        .group_by(AgentAuditLog.tier_used)
    )
    tier_rows = (await db.execute(tier_stmt)).all()
    distribution = {tier: count for tier, count in tier_rows}

    return {
        "date": date.today().isoformat(),
        "total_queries": int(row.count),
        "total_cost_usd": float(row.cost or 0),
        "success_count": int(row.success_count),
        "p95_latency_ms": float(row.p95_latency or 0),
        "tier_distribution": distribution,
    }


@router.get("/top-expensive", dependencies=[Depends(_verify_api_key)])
async def top_expensive(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Top N highest-cost queries today (cost_usd DESC)."""
    return await _top_n(db, AgentAuditLog.cost_usd, limit, descending=True)


@router.get("/top-slow", dependencies=[Depends(_verify_api_key)])
async def top_slow(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Top N slowest queries today (total_latency_ms DESC)."""
    return await _top_n(db, AgentAuditLog.total_latency_ms, limit, descending=True)


@router.get("/failures", dependencies=[Depends(_verify_api_key)])
async def recent_failures(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Recent failed / unclear queries today.

    Ordered by recency so an operator can spot a fresh regression
    without wading through ancient noise."""
    since = _today_start_utc()
    stmt = (
        select(AgentAuditLog)
        .where(
            AgentAuditLog.query_timestamp >= since,
            AgentAuditLog.success.is_(False),
        )
        .order_by(desc(AgentAuditLog.query_timestamp))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]


@router.get("/cost-trend", dependencies=[Depends(_verify_api_key)])
async def cost_trend(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Daily cost totals over the last ``days`` calendar days.

    Returns oldest-first so a chart consumer can render left-to-right
    without sorting client-side."""
    if days <= 0 or days > 60:
        raise HTTPException(status_code=400, detail="days must be 1..60")
    since = _today_start_utc() - timedelta(days=days - 1)
    day_col = func.date_trunc("day", AgentAuditLog.query_timestamp).label("day")
    stmt = (
        select(
            day_col,
            func.count().label("count"),
            func.coalesce(func.sum(AgentAuditLog.cost_usd), 0).label("cost"),
        )
        .where(AgentAuditLog.query_timestamp >= since)
        .group_by(day_col)
        .order_by(day_col.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "day": r.day.date().isoformat(),
            "queries": int(r.count),
            "cost_usd": float(r.cost or 0),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _top_n(
    db: AsyncSession,
    column,
    limit: int,
    *,
    descending: bool,
) -> list[dict[str, Any]]:
    if limit <= 0 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be 1..100")
    since = _today_start_utc()
    order = desc(column) if descending else column.asc()
    stmt = (
        select(AgentAuditLog)
        .where(
            AgentAuditLog.query_timestamp >= since,
            column.is_not(None),
        )
        .order_by(order)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(r: AgentAuditLog) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "user_id": str(r.user_id) if r.user_id else None,
        "query_text": r.query_text,
        "query_timestamp": r.query_timestamp.isoformat(),
        "tier_used": r.tier_used,
        "routing_reason": r.routing_reason,
        "tool_call_count": r.tool_call_count,
        "llm_model": r.llm_model,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "cost_usd": float(r.cost_usd or 0),
        "success": r.success,
        "response_preview": r.response_preview,
        "error": r.error,
        "total_latency_ms": r.total_latency_ms,
    }
