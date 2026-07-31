from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin.deps import get_current_admin
from backend.database import get_db
from backend.models.admin_user import AdminUser
from backend.models.conversation_context import ConversationContext, ROLE_USER
from backend.models.cost_budget import LLMCostLog
from backend.models.portfolio_asset import PortfolioAsset
from backend.models.user import User
from backend.services.admin_audit import log_action
from backend.services.onboarding.wealth_inference_service import infer_segment
from backend.services.user_status_service import STATUSES as _SHARED_STATUSES
from backend.services.user_status_service import classify_status
from backend.utils.pii import mask_name
from backend.utils.time_human import humanize_vi

router = APIRouter(prefix="/users", tags=["admin-users"])

DEFAULT_TENANT_ID = 1
SORT_KEYS = {"last_active_desc", "cost_desc", "joined_desc", "messages_desc"}
TIERS = {"starter", "young_pro", "mass_affluent", "hnw"}
STATUSES = set(_SHARED_STATUSES)


class AdminUserListItem(BaseModel):
    user_id: str
    telegram_id: int
    telegram_username: str | None = None
    display_name: str
    tier: str
    joined_at: str
    last_active_at: str | None = None
    last_active_human: str
    messages_total: int
    tokens_total: int
    llm_cost_total_usd: float
    assets_count: int
    status: str


class AdminUserListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    users: list[AdminUserListItem]


class ActivityPoint(BaseModel):
    date: str
    messages: int


class AssetBreakdownItem(BaseModel):
    type: str
    count: int
    total_value_vnd: int


class CostByIntentItem(BaseModel):
    resolved_by: str
    calls: int
    total_cost_usd: float


class LicenseInfo(BaseModel):
    plan: str = "free"
    status: str = "active"
    trial_ends_at: str | None = None


class AdminUserDetailResponse(BaseModel):
    user_id: str
    telegram_id: int
    telegram_username: str | None = None
    display_name: str
    joined_at: str
    tier: str
    status: str
    timeline: list[ActivityPoint]
    assets: list[AssetBreakdownItem]
    cost_by_intent: list[CostByIntentItem]
    license: LicenseInfo


class StatusChangeRequest(BaseModel):
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=10, max_length=500)


def _admin_tenant_id(admin: AdminUser) -> int:
    return admin.tenant_id or DEFAULT_TENANT_ID


def _asset_value_expr():
    return func.coalesce(PortfolioAsset.quantity, 1) * func.coalesce(
        PortfolioAsset.current_price,
        PortfolioAsset.purchase_price,
        0,
    )


def _usd_from_vnd(value: Any) -> float:
    return round(float(value or 0) / 25_000, 6)


# Lifecycle status now lives in the shared ``user_status_service`` so the admin
# console and the re-engagement broadcast (Phase 4.5 E5 #5.2) classify "dormant"
# identically. Kept as a module-level alias so the two call sites below — and the
# admin tests — keep the same name.
_classify_status = classify_status


def _base_user_stats_stmt(tenant_id: int):
    msg_stats = (
        select(
            ConversationContext.user_id.label("user_id"),
            func.max(ConversationContext.created_at).label("last_active_at"),
            func.count(ConversationContext.id).label("messages_total"),
        )
        .where(ConversationContext.role == ROLE_USER)
        .group_by(ConversationContext.user_id)
        .subquery()
    )
    cost_stats = (
        select(
            LLMCostLog.user_id.label("user_id"),
            func.coalesce(
                func.sum(LLMCostLog.tokens_in + LLMCostLog.tokens_out), 0
            ).label("tokens_total"),
            func.coalesce(func.sum(LLMCostLog.cost_vnd), 0).label("cost_vnd"),
        )
        .where(LLMCostLog.tenant_id == tenant_id)
        .group_by(LLMCostLog.user_id)
        .subquery()
    )
    asset_stats = (
        select(
            PortfolioAsset.user_id.label("user_id"),
            func.count(PortfolioAsset.id).label("assets_count"),
            func.coalesce(func.sum(_asset_value_expr()), 0).label("total_asset_vnd"),
        )
        .where(
            PortfolioAsset.tenant_id == tenant_id, PortfolioAsset.deleted_at.is_(None)
        )
        .group_by(PortfolioAsset.user_id)
        .subquery()
    )
    return (
        select(
            User.id,
            User.telegram_id,
            User.telegram_handle,
            User.display_name,
            User.created_at,
            User.manual_status,
            msg_stats.c.last_active_at,
            func.coalesce(msg_stats.c.messages_total, 0).label("messages_total"),
            func.coalesce(cost_stats.c.tokens_total, 0).label("tokens_total"),
            func.coalesce(cost_stats.c.cost_vnd, 0).label("cost_vnd"),
            func.coalesce(asset_stats.c.assets_count, 0).label("assets_count"),
            func.coalesce(asset_stats.c.total_asset_vnd, 0).label("total_asset_vnd"),
        )
        .select_from(User)
        .outerjoin(msg_stats, msg_stats.c.user_id == User.id)
        .outerjoin(cost_stats, cost_stats.c.user_id == User.id)
        .outerjoin(asset_stats, asset_stats.c.user_id == User.id)
        .where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
    )


def _apply_sort(stmt, sort: str):
    if sort == "cost_desc":
        return stmt.order_by(
            desc(literal_column_safe("cost_vnd")), desc(User.created_at)
        )
    if sort == "joined_desc":
        return stmt.order_by(desc(User.created_at))
    if sort == "messages_desc":
        return stmt.order_by(
            desc(literal_column_safe("messages_total")), desc(User.created_at)
        )
    return stmt.order_by(
        desc(literal_column_safe("last_active_at")).nulls_last(), desc(User.created_at)
    )


def literal_column_safe(name: str):
    # Keep sort columns hard-coded, never user-controlled.
    from sqlalchemy import literal_column

    return literal_column(name)


def _row_to_list_item(row) -> AdminUserListItem:
    tier = infer_segment(Decimal(row.total_asset_vnd or 0))
    user_status = _classify_status(
        row.created_at, row.last_active_at, row.manual_status
    )
    return AdminUserListItem(
        user_id=str(row.id),
        telegram_id=row.telegram_id,
        telegram_username=row.telegram_handle,
        display_name=mask_name(row.display_name or row.telegram_handle),
        tier=tier,
        joined_at=row.created_at.date().isoformat(),
        last_active_at=row.last_active_at.isoformat() if row.last_active_at else None,
        last_active_human=humanize_vi(row.last_active_at),
        messages_total=int(row.messages_total or 0),
        tokens_total=int(row.tokens_total or 0),
        llm_cost_total_usd=_usd_from_vnd(row.cost_vnd),
        assets_count=int(row.assets_count or 0),
        status=user_status,
    )


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    search: str | None = Query(default=None, max_length=100),
    tier: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str = Query(default="last_active_desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    if sort not in SORT_KEYS:
        raise HTTPException(status_code=422, detail="Invalid sort")
    if tier is not None and tier not in TIERS:
        raise HTTPException(status_code=422, detail="Invalid tier")
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")

    tenant_id = _admin_tenant_id(admin)
    stmt = _base_user_stats_stmt(tenant_id)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                cast(User.id, String).ilike(pattern),
                cast(User.telegram_id, String).ilike(pattern),
                User.display_name.ilike(pattern),
                User.telegram_handle.ilike(pattern),
            )
        )
    stmt = _apply_sort(stmt, sort).limit(1000)
    rows = (await db.execute(stmt)).all()
    users = [_row_to_list_item(row) for row in rows]
    if tier:
        users = [item for item in users if item.tier == tier]
    if status:
        users = [item for item in users if item.status == status]
    return AdminUserListResponse(
        total=len(users),
        limit=limit,
        offset=offset,
        users=users[offset : offset + limit],
    )


async def _get_user_for_admin(db: AsyncSession, user_id: str, tenant_id: int) -> User:
    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        ) from exc
    user = await db.scalar(
        select(User).where(
            User.id == uid, User.tenant_id == tenant_id, User.deleted_at.is_(None)
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.get("/{user_id}", response_model=AdminUserDetailResponse)
async def get_user_detail(
    user_id: str,
    request: Request,
    reveal: bool = Query(default=False),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserDetailResponse:
    tenant_id = _admin_tenant_id(admin)
    user = await _get_user_for_admin(db, user_id, tenant_id)
    since = datetime.now(timezone.utc) - timedelta(days=30)

    timeline_rows = (
        await db.execute(
            select(
                func.date(ConversationContext.created_at).label("day"),
                func.count(ConversationContext.id).label("messages"),
            )
            .where(
                ConversationContext.user_id == user.id,
                ConversationContext.role == ROLE_USER,
                ConversationContext.created_at >= since,
            )
            .group_by(func.date(ConversationContext.created_at))
            .order_by(func.date(ConversationContext.created_at))
        )
    ).all()
    asset_rows = (
        await db.execute(
            select(
                PortfolioAsset.asset_type,
                func.count(PortfolioAsset.id).label("count"),
                func.coalesce(func.sum(_asset_value_expr()), 0).label(
                    "total_value_vnd"
                ),
            )
            .where(
                PortfolioAsset.user_id == user.id,
                PortfolioAsset.tenant_id == tenant_id,
                PortfolioAsset.deleted_at.is_(None),
            )
            .group_by(PortfolioAsset.asset_type)
            .order_by(PortfolioAsset.asset_type)
        )
    ).all()
    # The current cost ledger stores the routed LLM operation rather than a
    # message_id. Grouping on operation is the safest no-PII proxy for the
    # requested "cost by intent" panel until Phase 5 adds full support views.
    cost_rows = (
        await db.execute(
            select(
                func.coalesce(LLMCostLog.operation, "unknown").label("resolved_by"),
                func.count(LLMCostLog.id).label("calls"),
                func.coalesce(func.sum(LLMCostLog.cost_vnd), 0).label("cost_vnd"),
            )
            .where(
                LLMCostLog.user_id == user.id,
                LLMCostLog.tenant_id == tenant_id,
                LLMCostLog.created_at >= since,
            )
            .group_by(LLMCostLog.operation)
            .order_by(desc("cost_vnd"))
        )
    ).all()
    total_asset_vnd = sum(Decimal(row.total_value_vnd or 0) for row in asset_rows)
    last_active = await db.scalar(
        select(func.max(ConversationContext.created_at)).where(
            ConversationContext.user_id == user.id,
            ConversationContext.role == ROLE_USER,
        )
    )
    effective_status = _classify_status(
        user.created_at, last_active, user.manual_status
    )
    await log_action(
        db,
        admin.id,
        "pii_revealed" if reveal else "view_user_detail",
        target_type="user",
        target_id=str(user.id),
        payload={"reveal": reveal},
        request=request,
    )
    if reveal:
        await log_action(
            db,
            admin.id,
            "view_user_detail",
            target_type="user",
            target_id=str(user.id),
            payload={"reveal": reveal},
            request=request,
        )
    await db.commit()

    return AdminUserDetailResponse(
        user_id=str(user.id),
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_handle,
        display_name=(
            (user.display_name or user.telegram_handle or "—")
            if reveal
            else mask_name(user.display_name or user.telegram_handle)
        ),
        joined_at=user.created_at.isoformat(),
        tier=infer_segment(total_asset_vnd),
        status=effective_status,
        timeline=[
            ActivityPoint(date=str(row.day), messages=int(row.messages or 0))
            for row in timeline_rows
        ],
        assets=[
            AssetBreakdownItem(
                type=row.asset_type,
                count=int(row.count or 0),
                total_value_vnd=int(row.total_value_vnd or 0),
            )
            for row in asset_rows
        ],
        cost_by_intent=[
            CostByIntentItem(
                resolved_by=row.resolved_by or "unknown",
                calls=int(row.calls or 0),
                total_cost_usd=_usd_from_vnd(row.cost_vnd),
            )
            for row in cost_rows
        ],
        license=LicenseInfo(),
    )


@router.patch("/{user_id}/status")
async def change_user_status(
    user_id: str,
    body: StatusChangeRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    tenant_id = _admin_tenant_id(admin)
    user = await _get_user_for_admin(db, user_id, tenant_id)
    old_status = user.manual_status or "active"
    new_manual_status = "suspended" if body.status == "suspended" else None
    await db.execute(
        update(User).where(User.id == user.id).values(manual_status=new_manual_status)
    )
    await log_action(
        db,
        admin.id,
        "user_status_changed",
        target_type="user",
        target_id=str(user.id),
        payload={"from": old_status, "to": body.status, "reason": body.reason},
        request=request,
    )
    await db.commit()
    return {"user_id": str(user.id), "status": body.status}
