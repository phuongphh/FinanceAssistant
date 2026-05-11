"""Phase 4B Epic 2 — service tests with an in-memory fake AsyncSession.

We deliberately don't spin up Postgres for unit tests. A small fake session
that records ``add`` / ``flush`` / ``execute`` is enough to verify the
CRUD orchestration: real DB roundtrips happen in the integration tier.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from backend.life_events.schemas import LifeEventCreate, LifeEventUpdate
from backend.life_events import service as life_event_service
from backend.models.life_event import LifeEvent, LifeEventType


# -----------------------------------------------------------------------------
# Minimal fake AsyncSession — records writes, lets us return canned reads.
# -----------------------------------------------------------------------------


class _FakeResult:
    """Mimics enough of SQLAlchemy's Result API for the service code paths."""

    def __init__(self, rows: list[Any]):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class FakeSession:
    """In-memory backing store keyed by event UUID."""

    def __init__(self) -> None:
        self.store: dict[uuid.UUID, LifeEvent] = {}
        self.flush_count = 0
        self.added: list[LifeEvent] = []
        # Used by the _last_filter_predicate to influence next execute() call.
        self._last_query_filter: dict[str, Any] = {}

    def add(self, obj: LifeEvent) -> None:
        # Mimic Postgres default — server-side gen_random_uuid().
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        obj.created_at = obj.created_at or datetime.now(timezone.utc)
        obj.updated_at = obj.updated_at or datetime.now(timezone.utc)
        if obj.is_active is None:
            obj.is_active = True
        self.added.append(obj)
        self.store[obj.id] = obj

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, stmt) -> _FakeResult:
        """Inspect the stmt's WHERE/ORDER clauses to pick which rows to return.

        We can't fully parse SQLAlchemy core statements without a real
        connection, so we cheat: get_by_id binds an ``LifeEvent.id == X``
        clause, list_for_user binds ``LifeEvent.user_id == X``. We pick
        rows by matching the compiled string.
        """
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        rows = list(self.store.values())
        # Apply soft-delete filter when present in the compiled SQL.
        if "deleted_at IS NULL" in compiled:
            rows = [r for r in rows if r.deleted_at is None]
        if "is_active IS true" in compiled or "is_active = true" in compiled:
            rows = [r for r in rows if r.is_active]
        # For ``get_by_id`` queries, filter by ``id`` token in the SQL string.
        for row in list(rows):
            if f"life_events.id = '{row.id}'" in compiled:
                rows = [row]
                break
        # Order by planned_date ASC, NULLs last.
        if "ORDER BY" in compiled:
            rows.sort(
                key=lambda r: (
                    r.planned_date is None,
                    r.planned_date or date.max,
                    r.created_at or datetime.min,
                )
            )
        return _FakeResult(rows)


@pytest.fixture
def fake_db():
    return FakeSession()


@pytest.fixture
def user_id():
    return uuid.uuid4()


# -----------------------------------------------------------------------------
# CRUD tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_life_event_with_preset_values(fake_db, user_id):
    payload = LifeEventCreate(
        event_type=LifeEventType.BUY_HOUSE,
        title="Mua nhà",
        planned_date=date(2028, 1, 1),
        one_time_cost=Decimal("3500000000"),
        recurring_monthly_delta=Decimal("-28000000"),
        recurring_duration_months=240,
    )
    event = await life_event_service.create_life_event(fake_db, user_id, payload)
    assert event.id is not None
    assert event.user_id == user_id
    assert event.event_type == "buy_house"
    assert event.one_time_cost == Decimal("3500000000")
    assert event.is_active is True
    assert fake_db.flush_count == 1


@pytest.mark.asyncio
async def test_zero_duration_normalized_to_none_at_schema_layer(fake_db, user_id):
    """LifeEventCreate must coerce 0 → None for recurring_duration_months."""
    payload = LifeEventCreate(
        event_type=LifeEventType.WEDDING,
        planned_date=date(2027, 1, 1),
        one_time_cost=Decimal("500000000"),
        recurring_monthly_delta=Decimal("0"),
        recurring_duration_months=0,  # zero in → None out
    )
    assert payload.recurring_duration_months is None


@pytest.mark.asyncio
async def test_soft_delete_marks_deleted_at(fake_db, user_id):
    payload = LifeEventCreate(
        event_type=LifeEventType.WEDDING,
        planned_date=date(2027, 6, 1),
        one_time_cost=Decimal("500000000"),
    )
    event = await life_event_service.create_life_event(fake_db, user_id, payload)
    ok = await life_event_service.soft_delete(fake_db, user_id, event.id)
    assert ok is True
    assert event.deleted_at is not None
    assert event.is_active is False


@pytest.mark.asyncio
async def test_soft_delete_returns_false_for_missing_event(fake_db, user_id):
    ok = await life_event_service.soft_delete(fake_db, user_id, uuid.uuid4())
    assert ok is False


@pytest.mark.asyncio
async def test_update_life_event_changes_fields(fake_db, user_id):
    payload = LifeEventCreate(
        event_type=LifeEventType.BUY_HOUSE,
        planned_date=date(2028, 1, 1),
        one_time_cost=Decimal("3500000000"),
    )
    event = await life_event_service.create_life_event(fake_db, user_id, payload)
    update = LifeEventUpdate(title="Mua nhà HCM", one_time_cost=Decimal("4000000000"))
    updated = await life_event_service.update_life_event(fake_db, user_id, event.id, update)
    assert updated is not None
    assert updated.title == "Mua nhà HCM"
    assert updated.one_time_cost == Decimal("4000000000")


@pytest.mark.asyncio
async def test_get_by_id_excludes_soft_deleted_by_default(fake_db, user_id):
    payload = LifeEventCreate(event_type=LifeEventType.WEDDING)
    event = await life_event_service.create_life_event(fake_db, user_id, payload)
    await life_event_service.soft_delete(fake_db, user_id, event.id)
    fresh = await life_event_service.get_by_id(fake_db, user_id, event.id)
    assert fresh is None
    # ``include_deleted=True`` should still find it.
    raw = await life_event_service.get_by_id(
        fake_db, user_id, event.id, include_deleted=True
    )
    assert raw is not None


@pytest.mark.asyncio
async def test_list_for_user_orders_by_planned_date(fake_db, user_id):
    a = await life_event_service.create_life_event(
        fake_db,
        user_id,
        LifeEventCreate(
            event_type=LifeEventType.BUY_HOUSE,
            planned_date=date(2030, 1, 1),
        ),
    )
    b = await life_event_service.create_life_event(
        fake_db,
        user_id,
        LifeEventCreate(
            event_type=LifeEventType.WEDDING,
            planned_date=date(2028, 5, 1),
        ),
    )
    rows = await life_event_service.list_for_user(fake_db, user_id)
    assert [r.id for r in rows] == [b.id, a.id]


@pytest.mark.asyncio
async def test_create_validates_recurring_negative_monthly(fake_db, user_id):
    # Recurring monthly delta can be negative (outflow) — must NOT raise.
    payload = LifeEventCreate(
        event_type=LifeEventType.FIRST_CHILD,
        planned_date=date(2029, 1, 1),
        recurring_monthly_delta=Decimal("-8000000"),
        recurring_duration_months=216,
    )
    event = await life_event_service.create_life_event(fake_db, user_id, payload)
    assert event.recurring_monthly_delta == Decimal("-8000000")
