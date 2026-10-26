"""CRUD for admin-curated Hóng hớt items (#1061).

Layer contract: flush only. The admin router owns the transaction and
commits once, together with the audit-log entry for the same action.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.social_buzz_item import SocialBuzzItem

# Fields an admin may set/change through the portal. ``created_by``,
# timestamps and ``deleted_at`` are owned by the service.
EDITABLE_FIELDS = (
    "title",
    "summary",
    "url",
    "image_url",
    "source_type",
    "category",
    "is_active",
)


async def create_item(
    db: AsyncSession, *, admin_id: int | None, data: dict[str, Any]
) -> SocialBuzzItem:
    item = SocialBuzzItem(
        created_by=admin_id,
        **{key: data[key] for key in EDITABLE_FIELDS if key in data},
    )
    if item.is_active is None:
        item.is_active = True
    db.add(item)
    await db.flush()
    return item


async def get_item(db: AsyncSession, item_id: uuid.UUID) -> SocialBuzzItem | None:
    """Live item by id; soft-deleted rows read as absent."""
    item = await db.get(SocialBuzzItem, item_id)
    if item is None or item.deleted_at is not None:
        return None
    return item


async def update_item(
    db: AsyncSession, item: SocialBuzzItem, changes: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Apply ``changes`` and return ``{field: {"from", "to"}}`` for the audit log."""
    diff: dict[str, dict[str, Any]] = {}
    for key in EDITABLE_FIELDS:
        if key not in changes:
            continue
        old, new = getattr(item, key), changes[key]
        if old != new:
            setattr(item, key, new)
            diff[key] = {"from": old, "to": new}
    if diff:
        item.updated_at = datetime.now(timezone.utc)
        await db.flush()
    return diff


async def soft_delete_item(db: AsyncSession, item: SocialBuzzItem) -> None:
    now = datetime.now(timezone.utc)
    item.deleted_at = now
    item.updated_at = now
    await db.flush()


def build_list_query(
    *,
    category: str | None = None,
    is_active: bool | None = None,
):
    """Filtered, newest-first SELECT over live items (no paging applied)."""
    stmt = select(SocialBuzzItem).where(SocialBuzzItem.deleted_at.is_(None))
    if category is not None:
        stmt = stmt.where(SocialBuzzItem.category == category)
    if is_active is not None:
        stmt = stmt.where(SocialBuzzItem.is_active.is_(is_active))
    return stmt.order_by(SocialBuzzItem.created_at.desc(), SocialBuzzItem.id.desc())


async def list_items(
    db: AsyncSession,
    *,
    category: str | None = None,
    is_active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[SocialBuzzItem]]:
    stmt = build_list_query(category=category, is_active=is_active)
    total = int(
        (await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())))
        or 0
    )
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return total, list(rows)
