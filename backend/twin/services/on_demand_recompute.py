from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session_factory
from backend.models.twin_habit_loop import TwinRecomputeLog
from backend.models.user import User
from backend.ports.notifier import get_notifier
from backend.twin.services import threshold_service
from backend.twin.services.causality_service import attribute_delta
from backend.twin.services.negative_delta_service import can_notify_negative
from backend.twin.services.twin_projection_service import compute_and_store

logger = logging.getLogger(__name__)

DEBOUNCE_WINDOW = timedelta(seconds=30)
IDEMPOTENCY_WINDOW = timedelta(seconds=60)
USER_LOCK_TTL_SECONDS = 30
BACKPRESSURE_PENDING_LIMIT = 100
MAX_RETRIES = 3

_pending: dict[uuid.UUID, "PendingRecompute"] = {}
_locks: set[uuid.UUID] = set()
_tasks: set[asyncio.Task] = set()
_last_notification_at: dict[uuid.UUID, datetime] = {}


@dataclass(slots=True)
class PendingRecompute:
    user_id: uuid.UUID
    event_id: str
    event_type: str
    amount_vnd: Decimal = Decimal("0")
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_count: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def merge(self, *, event_id: str, event_type: str, amount_vnd: Decimal, metadata: dict[str, Any] | None = None) -> None:
        self.event_id = event_id
        self.event_type = event_type
        self.amount_vnd += amount_vnd
        self.last_seen = datetime.now(timezone.utc)
        self.event_count += 1
        if metadata:
            self.metadata.update(metadata)


async def enqueue_event(
    *,
    user_id: uuid.UUID,
    event_id: str,
    event_type: str,
    amount_vnd: Decimal | int | float = Decimal("0"),
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Debounce user actions and schedule one last-write-wins recompute."""
    amount = Decimal(str(amount_vnd))
    if user_id in _pending:
        _pending[user_id].merge(event_id=event_id, event_type=event_type, amount_vnd=amount, metadata=metadata)
        return True
    pending = PendingRecompute(user_id=user_id, event_id=event_id, event_type=event_type, amount_vnd=amount, metadata=metadata or {})
    _pending[user_id] = pending
    task = asyncio.create_task(_debounced_process(user_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


async def _debounced_process(user_id: uuid.UUID) -> None:
    await asyncio.sleep(DEBOUNCE_WINDOW.total_seconds())
    pending = _pending.pop(user_id, None)
    if pending is None:
        return
    await process_pending(pending)


async def process_pending(pending: PendingRecompute) -> TwinRecomputeLog | None:
    if pending.user_id in _locks:
        _pending[pending.user_id] = pending
        return None
    _locks.add(pending.user_id)
    try:
        return await _process_with_retries(pending)
    finally:
        _locks.discard(pending.user_id)


async def _process_with_retries(pending: PendingRecompute) -> TwinRecomputeLog | None:
    delay = 0.2
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await _process_once(pending, attempt=attempt)
        except Exception:
            logger.exception("on-demand Twin recompute failed user=%s attempt=%s", pending.user_id, attempt)
            if attempt == MAX_RETRIES:
                return None
            await asyncio.sleep(delay)
            delay *= 2
    return None


async def _process_once(pending: PendingRecompute, *, attempt: int) -> TwinRecomputeLog:
    total_start = time.perf_counter()
    queue_ms = int((datetime.now(timezone.utc) - pending.first_seen).total_seconds() * 1000)
    skip_reason: str | None = None
    notified = False
    notify_ms = 0
    compute_start = time.perf_counter()
    session_factory = get_session_factory()
    async with session_factory() as db:
        previous_base = await _latest_base_net_worth(db, pending.user_id)
        await compute_and_store(db, pending.user_id, scenario="both")
        await db.flush()
        current_base = await _latest_base_net_worth(db, pending.user_id)
        compute_ms = int((time.perf_counter() - compute_start) * 1000)
        delta_abs = (current_base or Decimal("0")) - (previous_base or Decimal("0"))
        delta_pct = Decimal("0") if not previous_base else (delta_abs / previous_base * Decimal("100")).quantize(Decimal("0.01"))
        user = await db.get(User, pending.user_id)
        segment = getattr(user, "wealth_level", None) or getattr(user, "wealth_segment", None)
        cfg = await threshold_service.get_threshold_config(db, segment)
        noticeable = threshold_service.is_noticeable(segment, delta_pct, delta_abs, config=cfg)
        if len(_pending) > BACKPRESSURE_PENDING_LIMIT:
            skip_reason = "backpressure"
        elif not noticeable:
            skip_reason = "below_threshold"
        elif not _idempotency_allows(pending.user_id):
            skip_reason = "idempotent_window"
        elif delta_abs < 0 and not await can_notify_negative(db, pending.user_id):
            skip_reason = "negative_frequency_cap"
        if skip_reason is None and user and user.telegram_id:
            notify_start = time.perf_counter()
            await _notify(user.telegram_id, delta_abs=delta_abs, delta_pct=delta_pct)
            notify_ms = int((time.perf_counter() - notify_start) * 1000)
            notified = True
            _last_notification_at[pending.user_id] = datetime.now(timezone.utc)
        log = TwinRecomputeLog(
            event_id=pending.event_id,
            user_id=pending.user_id,
            event_type=pending.event_type,
            queue_ms=queue_ms,
            compute_ms=compute_ms,
            notify_ms=notify_ms,
            total_ms=int((time.perf_counter() - total_start) * 1000),
            delta_pct=delta_pct,
            delta_absolute_vnd=delta_abs,
            notified_bool=notified,
            skip_reason=skip_reason,
            metadata_={"event_count": pending.event_count, "attempt": attempt, **pending.metadata},
        )
        db.add(log)
        await db.commit()
        return log


async def _latest_base_net_worth(db: AsyncSession, user_id: uuid.UUID) -> Decimal | None:
    from backend.models.twin_projection import TwinProjection
    result = await db.execute(
        select(TwinProjection.base_net_worth).where(TwinProjection.user_id == user_id).order_by(TwinProjection.computed_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


def _idempotency_allows(user_id: uuid.UUID) -> bool:
    last = _last_notification_at.get(user_id)
    if last is None:
        return True
    return datetime.now(timezone.utc) - last >= IDEMPOTENCY_WINDOW


async def _notify(chat_id: int, *, delta_abs: Decimal, delta_pct: Decimal) -> None:
    direction = "nhích lên" if delta_abs >= 0 else "nhích xuống"
    text = f"🔮 Twin vừa {direction} {abs(delta_pct)}%. Bấm ‘Vì sao Twin thay đổi?’ để xem chi tiết."
    await get_notifier().send_message(chat_id=chat_id, text=text, reply_markup={"inline_keyboard": [[{"text": "Vì sao Twin thay đổi?", "callback_data": "twin:causality"}, {"text": "Việc nên làm tiếp →", "callback_data": "twin:action"}]]})


def pending_recompute_count() -> int:
    return len(_pending)


async def build_causality_for_latest(db: AsyncSession, user_id: uuid.UUID) -> str:
    return (await attribute_delta(db, user_id)).text
