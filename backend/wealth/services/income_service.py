"""IncomeStream CRUD + monthly aggregation.

Distinct from ``backend.services.income_service`` (which manages
``IncomeRecord`` — historical receipts). Streams are *templates*
(recurring sources) — a salary, a quarterly dividend, a monthly
rent. Records are individual receipts of those streams.

Design goals:
- One-place math: ``IncomeStream.monthly_equivalent`` does all the
  schedule normalisation (monthly/quarterly/annually/ad-hoc). Every
  consumer (briefing, threshold service, agent tool, menu list)
  reads through this property.
- ``get_income_breakdown`` returns a ready-to-render DTO so callers
  don't re-aggregate per template.
- Auto-link FK: ``source_asset_id`` is now first-class (Epic 2
  promotion from Epic 1's JSONB). Lookups for "the rental stream
  for this asset" are O(1) via the partial index.

Layer contract: service flushes only — caller (router/worker) commits.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.income_types import (
    ScheduleType,
    is_passive_default,
)
from backend.wealth.models.income_stream import IncomeStream
from backend.wealth.schemas.income import (
    IncomeBreakdown,
    IncomeStreamCreate,
    IncomeStreamUpdate,
)


# ---------------------------------------------------------------------
# Mutation API
# ---------------------------------------------------------------------


async def create_income_stream(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: IncomeStreamCreate,
) -> IncomeStream:
    """Create a new stream after Pydantic validation has cleaned the
    payload. Falls back to the YAML default for ``is_passive`` when
    the caller didn't override.

    Defaults:
    - ``start_date`` defaults to today — most users add a stream for
      income that's already happening, not future-dated.
    - ``is_passive`` is derived from ``stream_type`` via
      ``is_passive_default`` so the wizard can skip the question for
      the 95% case.
    """
    stream_type = (
        data.stream_type.value
        if hasattr(data.stream_type, "value")
        else str(data.stream_type)
    )
    schedule_type = (
        data.schedule_type.value
        if hasattr(data.schedule_type, "value")
        else str(data.schedule_type)
    )
    is_passive = (
        data.is_passive
        if data.is_passive is not None
        else is_passive_default(stream_type)
    )
    start_date = data.start_date or date.today()

    stream = IncomeStream(
        user_id=user_id,
        stream_type=stream_type,
        is_passive=is_passive,
        name=data.name,
        notes=data.notes,
        amount=Decimal(data.amount),
        currency=data.currency or "VND",
        schedule_type=schedule_type,
        schedule_day=data.schedule_day,
        schedule_month=data.schedule_month,
        start_date=start_date,
        end_date=data.end_date,
        is_active=True,
        source_asset_id=data.source_asset_id,
    )
    db.add(stream)
    await db.flush()
    return stream


async def update_income_stream(
    db: AsyncSession,
    user_id: uuid.UUID,
    stream_id: uuid.UUID,
    updates: IncomeStreamUpdate,
) -> IncomeStream:
    """Apply a partial update (only fields explicitly set in
    ``updates``). Returns the mutated row.

    Raises ``ValueError`` when the stream doesn't exist or belongs
    to another user.
    """
    stream = await _get_owned(db, user_id, stream_id)
    if stream is None:
        raise ValueError(f"Income stream {stream_id} not found for user {user_id}")

    payload = updates.model_dump(exclude_unset=True)
    # Pydantic with ``use_enum_values=True`` already strips enums to
    # strings, so direct assignment is fine here.
    for field, value in payload.items():
        setattr(stream, field, value)
    stream.updated_at = datetime.utcnow()
    await db.flush()
    return stream


async def pause_stream(
    db: AsyncSession, user_id: uuid.UUID, stream_id: uuid.UUID
) -> IncomeStream:
    """Set ``is_active=False`` — distinct from "ended" (``end_date``).

    Used when income temporarily stops (tenant moves out, freelance
    contract on hold) but might resume. ``resume_stream`` flips it
    back. The stream remains queryable for historical reporting.
    """
    stream = await _get_owned(db, user_id, stream_id)
    if stream is None:
        raise ValueError(f"Income stream {stream_id} not found")
    stream.is_active = False
    stream.updated_at = datetime.utcnow()
    await db.flush()
    return stream


async def resume_stream(
    db: AsyncSession, user_id: uuid.UUID, stream_id: uuid.UUID
) -> IncomeStream:
    """Reverse of ``pause_stream``. Idempotent: already-active stream
    gets its ``updated_at`` bumped but no behavioural change."""
    stream = await _get_owned(db, user_id, stream_id)
    if stream is None:
        raise ValueError(f"Income stream {stream_id} not found")
    stream.is_active = True
    stream.updated_at = datetime.utcnow()
    await db.flush()
    return stream


async def delete_stream(
    db: AsyncSession, user_id: uuid.UUID, stream_id: uuid.UUID
) -> bool:
    """Hard-delete a stream. Used by the wizard's "❌ Xoá" button for
    cases where the user mis-entered (analogous to asset-undo). For
    "stream ended naturally", set ``end_date`` instead so reports
    can still reference it.

    Returns True if a row was deleted, False if not found / not owned.
    """
    stream = await _get_owned(db, user_id, stream_id)
    if stream is None:
        return False
    await db.delete(stream)
    await db.flush()
    return True


# ---------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------


async def get_active_streams(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    stream_type: str | None = None,
    is_passive: bool | None = None,
    include_inactive: bool = False,
) -> list[IncomeStream]:
    """List a user's streams with optional filters.

    Default: only ``is_active=True``. Set ``include_inactive=True``
    for historical/audit views. ``stream_type`` and ``is_passive``
    filters use the indexed ``(user_id, stream_type, is_active)``
    path so the agent's "thu nhập thụ động" call is O(matching rows).
    """
    stmt = select(IncomeStream).where(IncomeStream.user_id == user_id)
    if not include_inactive:
        stmt = stmt.where(IncomeStream.is_active.is_(True))
    if stream_type is not None:
        stmt = stmt.where(IncomeStream.stream_type == stream_type)
    if is_passive is not None:
        stmt = stmt.where(IncomeStream.is_passive.is_(is_passive))
    stmt = stmt.order_by(IncomeStream.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def get_stream_by_id(
    db: AsyncSession, user_id: uuid.UUID, stream_id: uuid.UUID
) -> IncomeStream | None:
    """Ownership-checked single-row fetch (mirrors asset_service)."""
    return await _get_owned(db, user_id, stream_id)


async def get_income_breakdown(
    db: AsyncSession, user_id: uuid.UUID
) -> IncomeBreakdown:
    """Return active/passive split + per-type breakdown.

    Pure aggregation in Python — at expected scale (≤20 streams per
    user) the per-row property access is faster than a CASE-WHEN SQL
    that duplicates ``monthly_equivalent`` math.
    """
    streams = await get_active_streams(db, user_id)
    total = Decimal(0)
    active = Decimal(0)
    passive = Decimal(0)
    by_type: dict[str, Decimal] = {}
    for s in streams:
        monthly = s.monthly_equivalent
        total += monthly
        if s.is_passive:
            passive += monthly
        else:
            active += monthly
        by_type[s.stream_type] = by_type.get(s.stream_type, Decimal(0)) + monthly

    passive_ratio: float | None
    if total <= 0:
        passive_ratio = None
    else:
        passive_ratio = float(passive / total * Decimal(100))

    return IncomeBreakdown(
        total_monthly=total,
        active_income=active,
        passive_income=passive,
        passive_ratio=passive_ratio,
        stream_count=len(streams),
        breakdown_by_type=by_type,
    )


async def get_total_monthly_income(
    db: AsyncSession, user_id: uuid.UUID
) -> Decimal:
    """Convenience wrapper used by ``threshold_service`` and the
    morning briefing. Equivalent to ``get_income_breakdown(...).
    total_monthly`` but skips the per-type aggregation when the
    caller only wants the headline number."""
    streams = await get_active_streams(db, user_id)
    return sum((s.monthly_equivalent for s in streams), Decimal(0))


# ---------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------


async def _get_owned(
    db: AsyncSession, user_id: uuid.UUID, stream_id: uuid.UUID
) -> IncomeStream | None:
    """Fetch with ownership check. We deliberately don't distinguish
    "wrong owner" from "no such row" so the API doesn't leak existence
    of other users' streams."""
    stmt = select(IncomeStream).where(
        IncomeStream.id == stream_id,
        IncomeStream.user_id == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()
