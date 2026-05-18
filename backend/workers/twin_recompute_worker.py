from __future__ import annotations

from backend.twin.services.on_demand_recompute import enqueue_event
from infra.event_bus.twin_events import TwinEvent, subscribe


async def handle_twin_event(event: TwinEvent) -> None:
    await enqueue_event(
        user_id=event.user_id,
        event_id=event.event_id,
        event_type=event.event_type,
        amount_vnd=event.amount_vnd,
        metadata=event.metadata,
    )


def register() -> None:
    subscribe(handle_twin_event)


register()
