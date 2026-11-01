"""Admin CRUD for Hóng hớt items (#1061).

Phase 1 of the "Hóng hớt" digest is curated by hand: the operator types
hot Threads/TikTok/tech/economy items into the admin portal
(``betien-admin`` → "Hóng hớt"). This router is that portal's API.

Auth is the admin portal's JWT (``backend.utils.admin_security`` via
:func:`backend.api.admin.deps.get_current_admin`), not the
``INTERNAL_API_KEY`` the operator-diagnostic routers use: the SPA holds a
bearer token, and every write here is attributed to the admin who made
it (``created_by`` + an ``admin_audit_log`` row). Mounted under
``/api/admin`` alongside the other portal routers.

Layer contract: the router is the transaction boundary. The service only
flushes; each mutating endpoint commits exactly once, after the audit
entry for the same action has been added.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin.deps import get_current_admin
from backend.database import get_db
from backend.models.admin_user import AdminUser
from backend.models.social_buzz_item import SocialBuzzItem
from backend.services import social_buzz_service
from backend.services.admin_audit import log_action

router = APIRouter(prefix="/social-buzz", tags=["admin-social-buzz"])

SourceType = Literal["thread", "tiktok", "manual"]
Category = Literal["social", "tech", "economy"]

TITLE_MAX = 300
SUMMARY_MAX = 5000
URL_MAX = 2000
AUDIT_TARGET = "social_buzz_item"


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _clean_url(value: str | None) -> str | None:
    """Blank → None; otherwise must be an absolute http(s) URL.

    The portal renders these as links and <img> sources, so a
    ``javascript:`` or ``data:`` value is rejected here rather than
    trusted to the frontend.
    """
    value = _clean_text(value)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be an http(s) URL")
    return value


class _ItemFields(BaseModel):
    @field_validator("summary", mode="before", check_fields=False)
    @classmethod
    def _summary(cls, value):
        return _clean_text(value) if isinstance(value, str) else value

    @field_validator("url", "image_url", mode="before", check_fields=False)
    @classmethod
    def _urls(cls, value):
        return _clean_url(value) if isinstance(value, str) else value

    @field_validator("title", mode="before", check_fields=False)
    @classmethod
    def _title(cls, value):
        return value.strip() if isinstance(value, str) else value


class SocialBuzzCreate(_ItemFields):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    summary: str | None = Field(default=None, max_length=SUMMARY_MAX)
    url: str | None = Field(default=None, max_length=URL_MAX)
    image_url: str | None = Field(default=None, max_length=URL_MAX)
    source_type: SourceType = "manual"
    category: Category
    is_active: bool = True


class SocialBuzzUpdate(_ItemFields):
    """Partial update — only the fields present in the body change.

    Sending ``"url": null`` (or an empty string) clears an optional field;
    omitting it leaves it alone.
    """

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    summary: str | None = Field(default=None, max_length=SUMMARY_MAX)
    url: str | None = Field(default=None, max_length=URL_MAX)
    image_url: str | None = Field(default=None, max_length=URL_MAX)
    source_type: SourceType | None = None
    category: Category | None = None
    is_active: bool | None = None


class SocialBuzzItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str | None
    url: str | None
    image_url: str | None
    source_type: str
    category: str
    is_active: bool
    created_by: int | None
    created_at: datetime | None
    updated_at: datetime | None


class SocialBuzzListResponse(BaseModel):
    total: int
    items: list[SocialBuzzItemOut]


async def _load(db: AsyncSession, item_id: uuid.UUID) -> SocialBuzzItem:
    item = await social_buzz_service.get_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Social buzz item not found")
    return item


@router.get("", response_model=SocialBuzzListResponse)
async def list_social_buzz(
    category: Category | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SocialBuzzListResponse:
    total, items = await social_buzz_service.list_items(
        db, category=category, is_active=is_active, limit=limit, offset=offset
    )
    return SocialBuzzListResponse(
        total=total,
        items=[SocialBuzzItemOut.model_validate(item) for item in items],
    )


@router.get("/{item_id}", response_model=SocialBuzzItemOut)
async def get_social_buzz(
    item_id: uuid.UUID,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SocialBuzzItemOut:
    return SocialBuzzItemOut.model_validate(await _load(db, item_id))


@router.post("", response_model=SocialBuzzItemOut, status_code=201)
async def create_social_buzz(
    body: SocialBuzzCreate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SocialBuzzItemOut:
    item = await social_buzz_service.create_item(
        db, admin_id=admin.id, data=body.model_dump()
    )
    await log_action(
        db,
        admin.id,
        "social_buzz_created",
        target_type=AUDIT_TARGET,
        target_id=str(item.id),
        payload={"category": item.category, "source_type": item.source_type},
        request=request,
    )
    await db.commit()
    await db.refresh(item)
    return SocialBuzzItemOut.model_validate(item)


@router.patch("/{item_id}", response_model=SocialBuzzItemOut)
async def update_social_buzz(
    item_id: uuid.UUID,
    body: SocialBuzzUpdate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SocialBuzzItemOut:
    changes = body.model_dump(exclude_unset=True)
    # Required columns can be omitted but never cleared.
    for key in ("title", "source_type", "category", "is_active"):
        if key in changes and changes[key] is None:
            raise HTTPException(status_code=422, detail=f"{key} cannot be null")

    item = await _load(db, item_id)
    diff = await social_buzz_service.update_item(db, item, changes)
    if diff:
        await log_action(
            db,
            admin.id,
            "social_buzz_updated",
            target_type=AUDIT_TARGET,
            target_id=str(item.id),
            # Field names only — summaries can be long and the audit trail
            # needs "what changed", not a copy of the content.
            payload={"fields": sorted(diff)},
            request=request,
        )
        await db.commit()
        await db.refresh(item)
    return SocialBuzzItemOut.model_validate(item)


@router.delete("/{item_id}", status_code=204)
async def delete_social_buzz(
    item_id: uuid.UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft delete: the row stays (``deleted_at``), it just stops existing
    for the portal and the digest. Use PATCH ``is_active=false`` to hide an
    item while keeping it editable."""
    item = await _load(db, item_id)
    await social_buzz_service.soft_delete_item(db, item)
    await log_action(
        db,
        admin.id,
        "social_buzz_deleted",
        target_type=AUDIT_TARGET,
        target_id=str(item.id),
        request=request,
    )
    await db.commit()
    return Response(status_code=204)
