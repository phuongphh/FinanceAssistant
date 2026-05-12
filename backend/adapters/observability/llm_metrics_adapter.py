"""LLM metrics view helpers (Phase 4.1, Story A.5).

The raw write path is in ``backend.services.cost.budget_service``
(every tracked call inserts into ``llm_cost_log``). This module
provides read aggregation for the Metabase dashboard + the KPI digest:

- ``provider_p50_p95_latency(window)``
- ``error_rate_per_intent(window)``
- ``daily_active_users(window)``

Kept separate from ``cost_report_service`` so cost concerns (VND) and
ops concerns (latency, error rate) don't get tangled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.cost_budget import LLMCostLog


@dataclass
class ProviderLatency:
    provider: str
    p50_ms: int
    p95_ms: int
    error_rate: float
    sample_size: int


async def provider_latency_stats(
    db: AsyncSession, *, hours_back: int = 24
) -> list[ProviderLatency]:
    """Compute p50/p95 latency and error rate per provider over a window.

    Implementation note: PostgreSQL ``percentile_cont`` is the canonical
    way to compute percentiles; we use the WITHIN GROUP form. The query
    is bounded by ``hours_back`` to keep the scan cheap.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    stmt = (
        select(
            LLMCostLog.provider,
            func.percentile_cont(0.5)
            .within_group(LLMCostLog.latency_ms.asc())
            .label("p50"),
            func.percentile_cont(0.95)
            .within_group(LLMCostLog.latency_ms.asc())
            .label("p95"),
            func.count().label("total"),
            func.sum(func.case((LLMCostLog.success.is_(False), 1), else_=0)).label(
                "errors"
            ),
        )
        .where(LLMCostLog.created_at >= cutoff)
        .group_by(LLMCostLog.provider)
    )
    rows = (await db.execute(stmt)).all()
    out: list[ProviderLatency] = []
    for provider, p50, p95, total, errors in rows:
        total_i = int(total or 0)
        errors_i = int(errors or 0)
        out.append(
            ProviderLatency(
                provider=provider,
                p50_ms=int(p50 or 0),
                p95_ms=int(p95 or 0),
                error_rate=(errors_i / total_i) if total_i else 0.0,
                sample_size=total_i,
            )
        )
    return out
