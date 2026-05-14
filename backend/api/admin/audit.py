from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin.deps import get_current_admin
from backend.database import get_db
from backend.models.admin_audit_log import AdminAuditLog
from backend.models.admin_user import AdminUser
from backend.schemas.admin import AuditLogEntryOut, AuditLogListResponse
from backend.services.admin_audit import log_action

router = APIRouter(prefix="/audit", tags=["admin-audit"])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=100),
    target_type: str | None = Query(default=None, max_length=50),
    admin_user_id: int | None = Query(default=None, ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    filters = []
    if action:
        filters.append(AdminAuditLog.action == action)
    if target_type:
        filters.append(AdminAuditLog.target_type == target_type)
    if admin_user_id:
        filters.append(AdminAuditLog.admin_user_id == admin_user_id)

    total_stmt = select(func.count()).select_from(AdminAuditLog)
    list_stmt = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
    if filters:
        total_stmt = total_stmt.where(*filters)
        list_stmt = list_stmt.where(*filters)

    total = await db.scalar(total_stmt)
    result = await db.execute(list_stmt.limit(limit).offset(offset))
    entries = [AuditLogEntryOut.model_validate(entry) for entry in result.scalars().all()]
    await log_action(
        db,
        admin.id,
        "audit_list",
        target_type="admin_audit_log",
        payload={
            "limit": limit,
            "offset": offset,
            "action": action,
            "target_type": target_type,
            "admin_user_id": admin_user_id,
        },
        request=request,
    )
    await db.commit()
    return AuditLogListResponse(total=int(total or 0), limit=limit, offset=offset, entries=entries)
