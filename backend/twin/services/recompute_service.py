"""On-demand Financial Twin recompute trigger.

The webhook/update critical path only decides and enqueues. The actual Monte
Carlo work runs in a background task with its own session and commit boundary.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session_factory
from backend.twin.services.twin_projection_service import compute_and_store
from backend.twin.services.twin_query_service import get_latest_projection
from backend.wealth.services import net_worth_calculator as wealth_service

logger = logging.getLogger(__name__)

RECOMPUTE_THRESHOLD = Decimal("0.05")
DEBOUNCE_WINDOW = timedelta(hours=1)
_pending_user_ids: set[uuid.UUID] = set()
_pending_tasks: set[asyncio.Task] = set()


async def should_recompute(
    db: AsyncSession,
    user_id: uuid.UUID,
    delta_net_worth: Decimal,
    *,
    now: datetime | None = None,
) -> bool:
    """Return true when an asset edit is large enough and not debounced."""
    now = now or datetime.now(timezone.utc)
    if user_id in _pending_user_ids:
        return False

    latest = await get_latest_projection(db, user_id)
    if latest is not None:
        computed_at = latest.computed_at
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)
        if now - computed_at < DEBOUNCE_WINDOW:
            return False

    current = (await wealth_service.calculate_stored_current(db, user_id)).total
    baseline = max(current - Decimal(delta_net_worth), Decimal(0))
    ratio_base = current if current > 0 else baseline
    if ratio_base <= 0:
        return False
    return abs(Decimal(delta_net_worth)) / ratio_base >= RECOMPUTE_THRESHOLD


async def enqueue_recompute_if_needed(
    db: AsyncSession,
    user_id: uuid.UUID,
    delta_net_worth: Decimal,
) -> bool:
    """Schedule background recompute if threshold/debounce allow it."""
    if not await should_recompute(db, user_id, delta_net_worth):
        return False
    _pending_user_ids.add(user_id)
    task = asyncio.create_task(_compute_in_background(user_id))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
    return True


async def _compute_in_background(user_id: uuid.UUID) -> None:
    try:
        session_factory = get_session_factory()
        async with session_factory() as db:
            try:
                await compute_and_store(db, user_id, scenario="both")
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("twin-recompute: failed for user=%s", user_id)
    finally:
        _pending_user_ids.discard(user_id)


def pending_recompute_count() -> int:
    return len(_pending_user_ids)
