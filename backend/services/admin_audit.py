from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.admin_audit_log import AdminAuditLog


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()[:64]
    return request.client.host if request.client else None


async def log_action(
    db: AsyncSession,
    admin_id: int | None,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
    request: Request | None = None,
    commit: bool = False,
) -> AdminAuditLog:
    entry = AdminAuditLog(
        admin_user_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        ip_address=_client_ip(request),
        user_agent=(request.headers.get("user-agent")[:1000] if request and request.headers.get("user-agent") else None),
    )
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(entry)
    else:
        await db.flush()
    return entry
