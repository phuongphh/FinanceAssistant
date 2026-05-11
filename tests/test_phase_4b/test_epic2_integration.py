"""Phase 4B Epic 2 — light integration tests for the Telegram wizard.

We don't hit Telegram or Postgres. We stub send_message, send_photo, and
wizard_service so we can drive the state machine and assert it ends in
the expected wizard_state shape and triggers a recompute task.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import backend.bot.handlers.life_event_entry as handler_module
from backend.bot.handlers import life_event_entry as h
from backend.models.life_event import LifeEvent, LifeEventType


# -----------------------------------------------------------------------------
# Stubs
# -----------------------------------------------------------------------------


class FakeWizardService:
    """Records wizard_state transitions in memory."""

    def __init__(self):
        self.state: dict | None = None

    async def start_flow(self, db, user_id, flow, step, draft=None):
        self.state = {"flow": flow, "step": step, "draft": dict(draft or {})}
        return self.state

    async def update_step(self, db, user_id, step, draft_patch=None):
        if self.state is None:
            return None
        self.state["step"] = step
        if draft_patch:
            self.state["draft"].update(draft_patch)
        return self.state

    async def clear(self, db, user_id):
        self.state = None

    def get_state(self, *_a, **_k):
        return self.state

    def get_flow(self, state):
        return (state or {}).get("flow")

    def get_step(self, state):
        return (state or {}).get("step")

    def get_draft(self, state):
        return dict((state or {}).get("draft") or {})


class FakeLifeEventService:
    """In-memory store + matching API surface."""

    def __init__(self):
        self.events: dict[uuid.UUID, LifeEvent] = {}
        self.create_called = 0

    async def create_life_event(self, db, user_id, payload):
        self.create_called += 1
        event = LifeEvent()
        event.id = uuid.uuid4()
        event.user_id = user_id
        event.event_type = payload.event_type.value
        event.title = payload.title
        event.planned_date = payload.planned_date
        event.one_time_cost = payload.one_time_cost
        event.recurring_monthly_delta = payload.recurring_monthly_delta
        event.recurring_duration_months = payload.recurring_duration_months
        event.notes = payload.notes
        event.is_active = True
        event.created_at = datetime.now(timezone.utc)
        event.updated_at = event.created_at
        self.events[event.id] = event
        return event

    async def list_for_user(self, db, user_id, *, active_only=True):
        return [e for e in self.events.values() if e.user_id == user_id and e.is_active]

    async def get_by_id(self, db, user_id, event_id, *, include_deleted=False):
        return self.events.get(event_id)

    async def soft_delete(self, db, user_id, event_id):
        e = self.events.get(event_id)
        if e is None:
            return False
        e.is_active = False
        e.deleted_at = datetime.now(timezone.utc)
        return True


@pytest.fixture(autouse=True)
def stub_dependencies(monkeypatch):
    """Patch wizard_service, life_event_service, send_message/photo, analytics."""
    wizard = FakeWizardService()
    fake_service = FakeLifeEventService()

    monkeypatch.setattr(h, "wizard_service", wizard)
    monkeypatch.setattr(h, "life_event_service", fake_service)

    sent_messages: list[dict] = []

    async def fake_send_message(*, chat_id, text, **kwargs):
        sent_messages.append({"chat_id": chat_id, "text": text, **kwargs})

    async def fake_send_photo(**kwargs):
        sent_messages.append({"photo": True, **kwargs})

    async def fake_edit_message_text(**kwargs):
        sent_messages.append({"edit": True, **kwargs})

    async def fake_answer_callback(*args, **kwargs):
        return None

    monkeypatch.setattr(h, "send_message", fake_send_message)
    monkeypatch.setattr(h, "send_photo", fake_send_photo)
    monkeypatch.setattr(h, "edit_message_text", fake_edit_message_text)
    monkeypatch.setattr(h, "answer_callback", fake_answer_callback)

    async def fake_get_user_by_telegram_id(db, tid):
        return SimpleNamespace(id=uuid.uuid4(), wizard_state=wizard.state)

    monkeypatch.setattr(h, "get_user_by_telegram_id", fake_get_user_by_telegram_id)
    monkeypatch.setattr(
        h, "analytics", SimpleNamespace(track=lambda *a, **k: None)
    )

    # Block the background recompute — we just want to verify it was scheduled.
    scheduled: list = []

    def fake_create_task(coro, **kwargs):
        scheduled.append(coro)
        coro.close()  # don't actually run it

        class _Stub:
            def cancel(self):
                return None

        return _Stub()

    monkeypatch.setattr(handler_module.asyncio, "create_task", fake_create_task)

    return SimpleNamespace(
        wizard=wizard,
        service=fake_service,
        messages=sent_messages,
        scheduled=scheduled,
    )


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_add_flow_sets_picker_state(stub_dependencies):
    user = SimpleNamespace(id=uuid.uuid4(), wizard_state=None)
    await h.start_add_flow(db=None, chat_id=42, user=user)
    state = stub_dependencies.wizard.state
    assert state is not None
    assert state["flow"] == h.FLOW_PICKER
    assert any("Kế hoạch" in m.get("text", "") for m in stub_dependencies.messages)


@pytest.mark.asyncio
async def test_full_preset_flow_saves_event_and_schedules_recompute(stub_dependencies):
    user = SimpleNamespace(id=uuid.uuid4(), wizard_state=None)
    # 1. Pick the BUY_HOUSE preset.
    await h._handle_pick_type(db=None, chat_id=1, user=user, event_type=LifeEventType.BUY_HOUSE)
    assert stub_dependencies.wizard.state["flow"] == h.FLOW_PRESET
    assert stub_dependencies.wizard.state["draft"]["event_type"] == "buy_house"

    # 2. Use preset → wizard moves to ask_year (planned_date not set yet).
    user.wizard_state = stub_dependencies.wizard.state
    await h._handle_use_preset(db=None, chat_id=1, user=user)
    assert stub_dependencies.wizard.state["step"] == "ask_year"

    # 3. Provide a future year (within max horizon offset).
    today_year = datetime.now(timezone.utc).year
    target_year = today_year + 2
    await h._consume_year(
        db=None,
        chat_id=1,
        user=user,
        draft=stub_dependencies.wizard.state["draft"],
        flow=h.FLOW_PRESET,
        text_raw=str(target_year),
    )
    assert stub_dependencies.wizard.state["step"] == "confirm"
    assert "planned_date" in stub_dependencies.wizard.state["draft"]

    # 4. Confirm → service.create called, wizard cleared, recompute scheduled.
    user.wizard_state = stub_dependencies.wizard.state
    await h._handle_confirm(db=None, chat_id=1, user=user)
    assert stub_dependencies.service.create_called == 1
    assert stub_dependencies.wizard.state is None
    assert len(stub_dependencies.scheduled) == 1


@pytest.mark.asyncio
async def test_invalid_year_does_not_advance(stub_dependencies):
    user = SimpleNamespace(id=uuid.uuid4(), wizard_state=None)
    await h._handle_pick_type(db=None, chat_id=1, user=user, event_type=LifeEventType.WEDDING)
    user.wizard_state = stub_dependencies.wizard.state
    await h._handle_use_preset(db=None, chat_id=1, user=user)

    # Past year → should bounce back with invalid_year message; step unchanged.
    await h._consume_year(
        db=None,
        chat_id=1,
        user=user,
        draft=stub_dependencies.wizard.state["draft"],
        flow=h.FLOW_PRESET,
        text_raw="1999",
    )
    assert stub_dependencies.wizard.state["step"] == "ask_year"
    assert "planned_date" not in stub_dependencies.wizard.state["draft"]


@pytest.mark.asyncio
async def test_delete_confirm_marks_event_inactive(stub_dependencies):
    user = SimpleNamespace(id=uuid.uuid4(), wizard_state=None)
    # Seed an event directly through the fake service.
    payload = SimpleNamespace(
        event_type=LifeEventType.BUY_HOUSE,
        title="Mua nhà",
        planned_date=date(2028, 1, 1),
        one_time_cost=Decimal("3500000000"),
        recurring_monthly_delta=Decimal("-8000000"),
        recurring_duration_months=240,
        notes=None,
    )
    event = await stub_dependencies.service.create_life_event(None, user.id, payload)
    await h._handle_delete_confirm(db=None, chat_id=1, user=user, event_id=event.id)
    assert event.is_active is False


@pytest.mark.asyncio
async def test_custom_flow_collects_all_fields(stub_dependencies):
    user = SimpleNamespace(id=uuid.uuid4(), wizard_state=None)
    await h._handle_pick_type(db=None, chat_id=1, user=user, event_type=LifeEventType.CUSTOM)
    assert stub_dependencies.wizard.state["flow"] == h.FLOW_CUSTOM
    assert stub_dependencies.wizard.state["step"] == "ask_title"

    # Title
    await h._consume_title(
        db=None,
        chat_id=1,
        user=user,
        draft=stub_dependencies.wizard.state["draft"],
        text_raw="Du học Úc",
    )
    assert stub_dependencies.wizard.state["draft"]["title"] == "Du học Úc"

    # One-time amount
    await h._consume_one_time(
        db=None,
        chat_id=1,
        user=user,
        draft=stub_dependencies.wizard.state["draft"],
        text_raw="500 triệu",
    )
    assert stub_dependencies.wizard.state["draft"]["one_time_cost"] == "500000000"

    # Monthly (no sign → outflow default → stored as negative)
    await h._consume_monthly(
        db=None,
        chat_id=1,
        user=user,
        draft=stub_dependencies.wizard.state["draft"],
        text_raw="20 triệu",
    )
    assert Decimal(stub_dependencies.wizard.state["draft"]["recurring_monthly_delta"]) < 0

    # Duration
    await h._consume_duration(
        db=None,
        chat_id=1,
        user=user,
        draft=stub_dependencies.wizard.state["draft"],
        text_raw="24",
    )
    assert stub_dependencies.wizard.state["draft"]["recurring_duration_months"] == 24
    assert stub_dependencies.wizard.state["step"] == "ask_year"
