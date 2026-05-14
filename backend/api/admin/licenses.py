from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin.deps import get_current_admin
from backend.database import get_db
from backend.models.admin_user import AdminUser
from backend.models.license import License
from backend.models.user import User
from backend.schemas.admin import LicenseSummaryBucket, LicenseSummaryResponse
from backend.services.admin_cache import cache_get, cache_set

router = APIRouter(prefix="/licenses", tags=["admin-licenses"])

DEFAULT_TENANT_ID = 1


def _admin_tenant_id(admin: AdminUser) -> int:
    return admin.tenant_id or DEFAULT_TENANT_ID


def _bucket_rows(rows) -> list[LicenseSummaryBucket]:
    return [
        LicenseSummaryBucket(key=str(row.key), count=int(row.count or 0))
        for row in rows
    ]


@router.get("/summary", response_model=LicenseSummaryResponse)
async def license_summary(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> LicenseSummaryResponse | dict:
    """Read-only monetization foundation summary for the admin console.

    License management is intentionally deferred to Phase 5.7. This endpoint is
    scoped by admin tenant and returns aggregates only, avoiding PII exposure and
    keeping the dashboard inexpensive to load.
    """

    tenant_id = _admin_tenant_id(admin)
    cache_key = f"admin:tenant:{tenant_id}:licenses:summary"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    total_users_stmt = (
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
    )
    total_licenses_stmt = (
        select(func.count())
        .select_from(License)
        .join(User, User.id == License.user_id)
        .where(
            License.tenant_id == tenant_id,
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
    )
    missing_stmt = (
        select(func.count())
        .select_from(User)
        .outerjoin(License, License.user_id == User.id)
        .where(
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
            License.id.is_(None),
        )
    )
    plan_stmt = (
        select(License.plan.label("key"), func.count(License.id).label("count"))
        .join(User, User.id == License.user_id)
        .where(
            License.tenant_id == tenant_id,
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
        .group_by(License.plan)
        .order_by(License.plan)
    )
    status_stmt = (
        select(License.status.label("key"), func.count(License.id).label("count"))
        .join(User, User.id == License.user_id)
        .where(
            License.tenant_id == tenant_id,
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
        .group_by(License.status)
        .order_by(License.status)
    )

    total_users = int((await db.scalar(total_users_stmt)) or 0)
    total_licenses = int((await db.scalar(total_licenses_stmt)) or 0)
    missing_free_backfill = int((await db.scalar(missing_stmt)) or 0)
    plans = _bucket_rows((await db.execute(plan_stmt)).all())
    statuses = _bucket_rows((await db.execute(status_stmt)).all())

    payload = LicenseSummaryResponse(
        generated_at=datetime.now(timezone.utc),
        total_users=total_users,
        total_licenses=total_licenses,
        missing_free_backfill=missing_free_backfill,
        plans=plans,
        statuses=statuses,
    )
    serializable = payload.model_dump(mode="json")
    await cache_set(cache_key, serializable, ttl_seconds=60)
    return payload
