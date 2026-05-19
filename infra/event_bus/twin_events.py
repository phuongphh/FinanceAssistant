from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Awaitable, Callable

TWIN_RECOMPUTE_EVENT_TYPES = {
    "asset.created",
    "asset.updated",
    "income.added",
    "goal.milestone_reached",
}
# Global publish-time floor — protects pub/sub from sub-cent noise. Per-segment
# gating (100k / 500k / 2tr / 10tr) happens inside the worker once user segment
# is known. Matches the lowest segment floor so Starters still get every
# qualifying event through.
EXPENSE_MINIMUM_VND = Decimal("100000")


@dataclass(frozen=True, slots=True)
class TwinEvent:
    event_type: str
    user_id: uuid.UUID
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    amount_vnd: Decimal = Decimal("0")
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict | None = None


def should_trigger_recompute(event: TwinEvent) -> bool:
    if event.event_type == "expense.added":
        return abs(event.amount_vnd) >= EXPENSE_MINIMUM_VND
    return event.event_type in TWIN_RECOMPUTE_EVENT_TYPES


Subscriber = Callable[[TwinEvent], Awaitable[None]]
_subscribers: list[Subscriber] = []


def subscribe(handler: Subscriber) -> None:
    if handler not in _subscribers:
        _subscribers.append(handler)


async def publish(event: TwinEvent) -> None:
    if not should_trigger_recompute(event):
        return
    await asyncio.gather(*(handler(event) for handler in list(_subscribers)))
