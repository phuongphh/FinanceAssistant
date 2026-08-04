from __future__ import annotations

import ipaddress
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.admin_audit_log import AdminAuditLog


def _client_ip(request: Request | None) -> str | None:
    """The address written to the audit trail.

    Reads what edge middleware already resolved (``request.state.client_ip``,
    see ``backend/utils/client_ip.py``) rather than ``X-Forwarded-For``. The
    raw header is caller-supplied unless the connection came from a trusted
    proxy, and an audit record naming an address the subject chose is worse
    than one naming none: it points the investigation at whoever the attacker
    picked. Deciding trust here is not an option either — that needs settings,
    which a service must not read.

    Falling back to the transport peer keeps the record truthful if the stamp
    is ever missing: that address cannot be forged over TCP.
    """
    if request is None:
        return None
    candidate = getattr(request.state, "client_ip", None) or (
        request.client.host if request.client else None
    )
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        # ``ip_address`` is an INET column, so a non-address — the "unknown"
        # sentinel, or a test transport's hostname — would fail the insert
        # and take the audited action down with it.
        return None
    return candidate


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
