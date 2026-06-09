"""Admin Twin metrics cache warmer (Phase 4.3).

Background job that pre-populates the four Twin admin endpoints
(``funnel``, ``loop``, ``comprehension``, ``delta``) so the first
operator request after a TTL expiry never pays the 5-15s build cost.

Strategy: for every distinct ``tenant_id`` that has at least one
active admin account, call each route function with default params
(``period=30d``, no cohort, no segment). The default view IS what the
dashboard loads on first open — warming other permutations would
waste DB cycles for vanishingly rare query shapes.

Idempotent: the underlying ``_cached(key, build)`` helper writes to
Redis with SETEX, so re-running before TTL expiry is a cheap cache hit.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin import twin_metrics
from backend.database import get_session_factory
from backend.models.admin_user import AdminUser

logger = logging.getLogger(__name__)

DEFAULT_PERIOD = "30d"


async def _active_tenant_ids(db: AsyncSession) -> list[int]:
    rows = (
        await db.execute(
            select(AdminUser.tenant_id)
            .where(AdminUser.is_active.is_(True))
            .distinct()
        )
    ).all()
    seen: set[int] = set()
    for (tenant_id,) in rows:
        seen.add(tenant_id or twin_metrics.DEFAULT_TENANT_ID)
    return sorted(seen)


async def _warm_tenant(db: AsyncSession, tenant_id: int) -> int:
    synthetic_admin = AdminUser(
        id=0,
        email="cache-warmer@internal",
        password_hash="",
        tenant_id=tenant_id,
        is_active=True,
    )
    warmed = 0
    builders = (
        ("funnel", lambda: twin_metrics.engagement_funnel(
            period=DEFAULT_PERIOD, start_date=None, end_date=None,
            cohort_week=None, segment=None, admin=synthetic_admin, db=db,
        )),
        ("loop", lambda: twin_metrics.loop_health(
            period=DEFAULT_PERIOD, start_date=None, end_date=None,
            cohort_week=None, segment=None, admin=synthetic_admin, db=db,
        )),
        ("comprehension", lambda: twin_metrics.comprehension(
            period=DEFAULT_PERIOD, start_date=None, end_date=None,
            cohort_week=None, admin=synthetic_admin, db=db,
        )),
        ("delta", lambda: twin_metrics.delta_distribution(
            period=DEFAULT_PERIOD, start_date=None, end_date=None,
            segment=None, admin=synthetic_admin, db=db,
        )),
    )
    for section, call in builders:
        try:
            await call()
            warmed += 1
        except Exception:
            logger.warning(
                "admin_cache_warmer section=%s tenant=%s failed",
                section, tenant_id, exc_info=True,
            )
    return warmed


async def run_admin_cache_warmer() -> dict:
    """Scheduler entry point. Returns a small summary for logs."""
    session_factory = get_session_factory()
    total_sections = 0
    async with session_factory() as db:
        tenants = await _active_tenant_ids(db)
        for tenant_id in tenants:
            total_sections += await _warm_tenant(db, tenant_id)
    logger.info(
        "admin_cache_warmer tenants=%s sections=%d", tenants, total_sections
    )
    return {"tenants": tenants, "sections_warmed": total_sections}
