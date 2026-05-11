"""Life Event service — CRUD with soft delete.

Layer contract: this service flushes only. Routers/workers/handlers own the
transaction boundary. No ``db.commit()`` here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.life_events.schemas import (
    LifeEventCreate,
    LifeEventUpdate,
)
from backend.models.life_event import LifeEvent, LifeEventType


async def create_life_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    payload: LifeEventCreate,
) -> LifeEvent:
    """Persist a new life event. Returns the flushed row with ``id`` populated."""
    event = LifeEvent(
        user_id=user_id,
        event_type=payload.event_type.value,
        title=payload.title,
        planned_date=payload.planned_date,
        one_time_cost=payload.one_time_cost,
        recurring_monthly_delta=payload.recurring_monthly_delta,
        recurring_duration_months=payload.recurring_duration_months,
        notes=payload.notes,
        is_active=True,
    )
    db.add(event)
    await db.flush()
    return event


async def get_by_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> LifeEvent | None:
    """Return one event scoped to ``user_id``. Honours soft delete by default."""
    stmt = select(LifeEvent).where(
        LifeEvent.id == event_id, LifeEvent.user_id == user_id
    )
    if not include_deleted:
        stmt = stmt.where(LifeEvent.deleted_at.is_(None))
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    active_only: bool = True,
) -> list[LifeEvent]:
    """Return user's life events ordered by ``planned_date`` ascending.

    Events without a ``planned_date`` sort to the end so dated milestones come
    first in the UI — they're the ones that actually inject into MC paths.
    """
    stmt = (
        select(LifeEvent)
        .where(LifeEvent.user_id == user_id, LifeEvent.deleted_at.is_(None))
        .order_by(
            LifeEvent.planned_date.is_(None),
            LifeEvent.planned_date.asc(),
            LifeEvent.created_at.asc(),
        )
    )
    if active_only:
        stmt = stmt.where(LifeEvent.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def update_life_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: LifeEventUpdate,
) -> LifeEvent | None:
    event = await get_by_id(db, user_id, event_id)
    if event is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        # Normalize 0-month duration to None — same rule as the create schema.
        if field == "recurring_duration_months" and value == 0:
            value = None
        setattr(event, field, _coerce(field, value))
    event.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return event


async def soft_delete(
    db: AsyncSession,
    user_id: uuid.UUID,
    event_id: uuid.UUID,
) -> bool:
    """Soft delete by stamping ``deleted_at`` and flipping ``is_active``.

    Returns ``True`` if the row existed and was marked deleted. Idempotent:
    deleting an already-deleted row is treated as not-found.
    """
    event = await get_by_id(db, user_id, event_id)
    if event is None:
        return False
    event.deleted_at = datetime.now(timezone.utc)
    event.is_active = False
    event.updated_at = event.deleted_at
    await db.flush()
    return True


def _coerce(field: str, value):
    """Convert PATCH payload values to model-friendly types."""
    if value is None:
        return None
    if field in {"one_time_cost", "recurring_monthly_delta"}:
        return Decimal(str(value))
    return value


# --- helpers used by twin_projection_service when applying events to MC paths ---


def event_type_from_str(value: str) -> LifeEventType:
    try:
        return LifeEventType(value)
    except ValueError:
        return LifeEventType.CUSTOM
