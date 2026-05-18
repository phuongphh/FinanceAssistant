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
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session_factory
from backend.models.user import User
from backend.twin.services.twin_projection_service import compute_and_store
from backend.twin.services.twin_query_service import get_latest_projection
from backend.wealth.services import net_worth_calculator as wealth_service

logger = logging.getLogger(__name__)

RECOMPUTE_THRESHOLD = Decimal("0.05")
# Long debounce protects the engine against compute storms when the wallet
# is barely changing. Onboarding adds 4+ assets in <2 minutes and each one
# can swing the portfolio by 30%+, so the 30-minute hard block produced
# Twin projections stuck at the first asset's value. We now layer two
# windows: a short hard rate-limit + a long soft window that we only
# enforce while ``base_net_worth`` is close to ``current``. A divergent
# base bypasses the long window so the user's freshly-added 1.5 tỷ shows
# up in their Twin the next time they tap it.
DEBOUNCE_WINDOW = timedelta(minutes=30)
HARD_THROTTLE_WINDOW = timedelta(seconds=60)
BASE_DIVERGENCE_THRESHOLD = Decimal("0.05")
_pending_user_ids: set[uuid.UUID] = set()
_pending_tasks: set[asyncio.Task] = set()

_TWIN_COPY_PATH = Path(__file__).resolve().parents[4] / "content" / "twin_copy.yaml"


@lru_cache(maxsize=1)
def _load_recompute_copy() -> dict:
    with open(_TWIN_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("recompute", {})


async def should_recompute(
    db: AsyncSession,
    user_id: uuid.UUID,
    delta_net_worth: Decimal,
    *,
    now: datetime | None = None,
) -> bool:
    """Return true when an asset edit is large enough and not debounced.

    Layered gating:
    1. Skip if a recompute is already in flight for this user (concurrency).
    2. Skip if the last projection is younger than
       :data:`HARD_THROTTLE_WINDOW` — protects against compute storms on
       rapid edits.
    3. Skip if inside :data:`DEBOUNCE_WINDOW` **and** the last projection's
       ``base_net_worth`` is still within
       :data:`BASE_DIVERGENCE_THRESHOLD` of the current wallet. Onboarding
       used to add four 100tr+ assets back-to-back and the second through
       fourth were dropped here — the result was a Twin that anchored on
       a 50tr base while the user actually had 2.6 tỷ.
    4. Otherwise gate on edit size (``delta_net_worth >= 5% of current``).
    """
    now = now or datetime.now(timezone.utc)
    if user_id in _pending_user_ids:
        return False

    latest = await get_latest_projection(db, user_id)
    current = (await wealth_service.calculate_stored_current(db, user_id)).total
    if latest is not None:
        computed_at = latest.computed_at
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)
        elapsed = now - computed_at
        if elapsed < HARD_THROTTLE_WINDOW:
            return False
        if elapsed < DEBOUNCE_WINDOW and not _base_diverged(
            getattr(latest, "base_net_worth", None), current
        ):
            return False

    baseline = max(current - Decimal(delta_net_worth), Decimal(0))
    ratio_base = current if current > 0 else baseline
    if ratio_base <= 0:
        return False
    return abs(Decimal(delta_net_worth)) / ratio_base >= RECOMPUTE_THRESHOLD


def _base_diverged(stored_base: Decimal | None, current: Decimal) -> bool:
    """True when the stored projection's base no longer matches the wallet.

    Symmetric ratio (anchored to the larger side) so a 10x drop and a 10x
    rise both register as divergent without one side blowing past 100%.
    """
    base = abs(Decimal(stored_base or 0))
    actual = abs(Decimal(current or 0))
    denom = max(base, actual)
    if denom <= 0:
        return False
    return (abs(base - actual) / denom) > BASE_DIVERGENCE_THRESHOLD


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
        telegram_id: int | None = None
        async with session_factory() as db:
            try:
                result = await db.execute(
                    select(User.telegram_id).where(User.id == user_id)
                )
                telegram_id = result.scalar_one_or_none()
                await compute_and_store(db, user_id, scenario="both")
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("twin-recompute: failed for user=%s", user_id)
                return

        if telegram_id is not None:
            try:
                from backend.ports.notifier import get_notifier

                copy = _load_recompute_copy()
                text = copy.get("done", "🔮 Dự phóng Twin vừa được cập nhật!")
                notifier = get_notifier()
                await notifier.send_message(chat_id=telegram_id, text=text)
            except Exception:
                logger.warning(
                    "twin-recompute: notification failed for user=%s", user_id
                )
    finally:
        _pending_user_ids.discard(user_id)


def pending_recompute_count() -> int:
    return len(_pending_user_ids)
