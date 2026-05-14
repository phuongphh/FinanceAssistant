from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin.deps import extract_bearer_token, get_current_admin_any
from backend.database import get_db
from backend.models.admin_user import AdminUser
from backend.schemas.admin import AdminUserOut, ChangePasswordRequest, LoginRequest, LoginResponse
from backend.services.admin_audit import log_action
from backend.services.admin_auth import blacklist_token, check_login_rate_limit, record_login_attempt
from backend.utils.admin_security import create_admin_token, decode_admin_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["admin-auth"])


def _request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    ip_address = _request_ip(request)
    if not check_login_rate_limit(ip_address):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

    result = await db.execute(select(AdminUser).where(AdminUser.email == body.email))
    admin = result.scalar_one_or_none()
    valid = bool(admin and verify_password(body.password, admin.password_hash))
    if not valid:
        record_login_attempt(ip_address)
        await log_action(
            db,
            None,
            "login_failed",
            payload={"email": body.email},
            request=request,
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not admin.is_active:
        await log_action(db, admin.id, "login_blocked_inactive", request=request, commit=True)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    admin.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    token, _, expires_in = create_admin_token(
        admin.id,
        admin.email,
        admin.role,
        restricted=admin.force_password_change,
    )
    await log_action(db, admin.id, "login_success", request=request)
    await db.commit()
    await db.refresh(admin)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        force_password_change=admin.force_password_change,
        admin=admin,
    )


@router.post("/change-password", response_model=AdminUserOut)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin_any),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if not verify_password(body.current_password, admin.password_hash):
        await log_action(db, admin.id, "change_password_failed", request=request, commit=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    admin.password_hash = hash_password(body.new_password)
    admin.force_password_change = False
    await log_action(db, admin.id, "change_password_success", request=request)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.get("/me", response_model=AdminUserOut)
async def me(admin: AdminUser = Depends(get_current_admin_any)) -> AdminUser:
    return admin


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
    admin: AdminUser = Depends(get_current_admin_any),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    payload = decode_admin_token(extract_bearer_token(authorization))
    ttl = max(0, int(payload["exp"]) - int(time.time()))
    blacklist_token(str(payload["jti"]), ttl)
    await log_action(db, admin.id, "logout", request=request)
    await db.commit()
    return {"message": "Logged out"}
