from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.admin_user import AdminUser
from backend.services.admin_auth import is_token_blacklisted
from backend.utils.admin_security import decode_admin_token


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return authorization.split(" ", 1)[1].strip()


async def _resolve_admin(
    authorization: str | None,
    db: AsyncSession,
    *,
    allow_restricted: bool,
) -> AdminUser:
    payload = decode_admin_token(extract_bearer_token(authorization))
    if is_token_blacklisted(str(payload["jti"])):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    admin = await db.get(AdminUser, int(payload["admin_id"]))
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive admin")
    if payload.get("restricted") and not allow_restricted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Must change password first")
    return admin


async def get_current_admin(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    return await _resolve_admin(authorization, db, allow_restricted=False)


async def get_current_admin_any(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    return await _resolve_admin(authorization, db, allow_restricted=True)
