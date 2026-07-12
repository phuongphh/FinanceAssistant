"""Phase 4.4 Epic 3 — Proactive Companion.

Covers the new ``onboarding_no_twin_return`` empathy trigger (fire /
no-fire across the activation window, twin-return threshold, cooldown),
the ``include_proactive`` gate on ``check_all_triggers`` (flag off → new
trigger skipped while pre-existing triggers still fire), the
``PROACTIVE_COMPANION_ENABLED`` flag read at the job edge, and that the
hourly job picks the trigger up with no per-trigger wiring change.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.bot.personality import empathy_engine
from backend.bot.personality.empathy_engine import (
    ONBOARDING_SILENCE_MAX_DAYS,
    ONBOARDING_SILENCE_MIN_DAYS,
)

NOW = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)


# ----- fakes ------------------------------------------------------------


class _FakeResult:
    def __init__(self, scalar):
        self._scalar = scalar

    def scalar_one(self):
        return self._scalar


class _FakeDB:
    """Returns a canned distinct-twin-view-days count for any query."""

    def __init__(self, *, twin_view_days=0):
        self._twin_view_days = twin_view_days

    async def execute(self, _stmt):
        return _FakeResult(self._twin_view_days)


def _user(*, days_ago_onboarded, completed=True, naive=False):
    if not completed:
        completed_at = None
    else:
        completed_at = NOW - timedelta(days=days_ago_onboarded)
        if naive:
            completed_at = completed_at.replace(tzinfo=None)
    return SimpleNamespace(
        id=uuid.uuid4(),
        onboarding_completed_at=completed_at,
        salutation="anh",
        get_greeting_name=lambda: "Minh",
    )


# ----- _check_onboarding_no_twin_return (unit) --------------------------


@pytest.mark.asyncio
async def test_fires_in_window_with_no_return_view():
    user = _user(days_ago_onboarded=ONBOARDING_SILENCE_MIN_DAYS + 1)
    # Onboarding writes no TwinViewEvent, so a user who never came back
    # has 0 distinct view days.
    db = _FakeDB(twin_view_days=0)

    trigger = await empathy_engine._check_onboarding_no_twin_return(db, user, NOW)

    assert trigger is not None
    assert trigger.name == "onboarding_no_twin_return"
    assert trigger.cooldown_days == 30
    assert trigger.context["days_since_onboarding"] == ONBOARDING_SILENCE_MIN_DAYS + 1


@pytest.mark.asyncio
async def test_no_fire_when_not_onboarded():
    user = _user(days_ago_onboarded=5, completed=False)
    db = _FakeDB(twin_view_days=0)

    assert await empathy_engine._check_onboarding_no_twin_return(db, user, NOW) is None


@pytest.mark.asyncio
async def test_no_fire_before_window_opens():
    # Onboarded today — too soon to nudge.
    user = _user(days_ago_onboarded=ONBOARDING_SILENCE_MIN_DAYS - 1)
    db = _FakeDB(twin_view_days=0)

    assert await empathy_engine._check_onboarding_no_twin_return(db, user, NOW) is None


@pytest.mark.asyncio
async def test_no_fire_after_window_closes():
    # Past the activation window — generic silent-N-days triggers own this.
    user = _user(days_ago_onboarded=ONBOARDING_SILENCE_MAX_DAYS + 1)
    db = _FakeDB(twin_view_days=0)

    assert await empathy_engine._check_onboarding_no_twin_return(db, user, NOW) is None


@pytest.mark.asyncio
async def test_no_fire_when_user_returned_to_twin():
    # Came back to the Twin at least once after onboarding (>= 1 distinct
    # view day) — no nudge. Onboarding itself writes no view event.
    user = _user(days_ago_onboarded=ONBOARDING_SILENCE_MIN_DAYS + 2)
    db = _FakeDB(twin_view_days=1)

    assert await empathy_engine._check_onboarding_no_twin_return(db, user, NOW) is None


@pytest.mark.asyncio
async def test_naive_completed_at_is_treated_as_utc():
    user = _user(days_ago_onboarded=ONBOARDING_SILENCE_MIN_DAYS + 1, naive=True)
    db = _FakeDB(twin_view_days=0)

    trigger = await empathy_engine._check_onboarding_no_twin_return(db, user, NOW)
    assert trigger is not None  # no crash on a naive datetime


# ----- include_proactive gate on check_all_triggers ---------------------


def _async_none(*_a, **_k):
    async def _inner(db, user, now):
        return None

    return _inner


def _async_trigger(name, priority):
    async def _inner(db, user, now):
        return empathy_engine.EmpathyTrigger(
            name=name, priority=priority, cooldown_days=1, context={}
        )

    return _inner


def _silence_all_checks(monkeypatch):
    for fn_name in (
        "_check_large_transaction",
        "_check_payday_splurge",
        "_check_over_budget_monthly",
        "_check_onboarding_no_twin_return",
        "_check_user_silent_7_days",
        "_check_user_silent_30_days",
        "_check_weekend_high_spending",
        "_check_first_saving_month",
        "_check_consecutive_over_budget",
    ):
        monkeypatch.setattr(empathy_engine, fn_name, _async_none())


@pytest.mark.asyncio
async def test_flag_on_new_trigger_fires(monkeypatch):
    _silence_all_checks(monkeypatch)
    # New trigger matches; a pre-existing ambient one also matches but sits
    # later in the order, so the new (proactive) trigger wins.
    monkeypatch.setattr(
        empathy_engine,
        "_check_onboarding_no_twin_return",
        _async_trigger("onboarding_no_twin_return", 3),
    )
    monkeypatch.setattr(
        empathy_engine, "_check_user_silent_7_days", _async_trigger("old", 4)
    )

    async def _never(*_a, **_k):
        return False

    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never)

    trigger = await empathy_engine.check_all_triggers(
        _FakeDB(), _user(days_ago_onboarded=5), now=NOW, include_proactive=True
    )
    assert trigger is not None
    assert trigger.name == "onboarding_no_twin_return"


@pytest.mark.asyncio
async def test_flag_off_skips_new_trigger_but_old_still_fires(monkeypatch):
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine,
        "_check_onboarding_no_twin_return",
        _async_trigger("onboarding_no_twin_return", 3),
    )
    monkeypatch.setattr(
        empathy_engine, "_check_user_silent_7_days", _async_trigger("old", 4)
    )

    async def _never(*_a, **_k):
        return False

    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never)

    trigger = await empathy_engine.check_all_triggers(
        _FakeDB(), _user(days_ago_onboarded=5), now=NOW, include_proactive=False
    )
    # New trigger skipped; the pre-existing trigger still fires.
    assert trigger is not None
    assert trigger.name == "old"


@pytest.mark.asyncio
async def test_cooldown_suppresses_new_trigger(monkeypatch):
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine,
        "_check_onboarding_no_twin_return",
        _async_trigger("onboarding_no_twin_return", 3),
    )

    async def _on_cooldown(*_a, **_k):
        return True

    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _FakeDB(), _user(days_ago_onboarded=5), now=NOW, include_proactive=True
    )
    assert trigger is None


# ----- render_message threads salutation --------------------------------


def test_render_message_threads_salutation():
    empathy_engine.reload_messages_for_tests()
    trigger = empathy_engine.EmpathyTrigger(
        name="onboarding_no_twin_return",
        priority=3,
        cooldown_days=30,
        context={"days_since_onboarding": 5},
    )
    user = SimpleNamespace(
        salutation="anh", get_greeting_name=lambda: "Minh"
    )
    msg = empathy_engine.render_message(trigger, user)

    assert msg.strip()
    assert "anh" in msg
    assert "Twin" in msg
    # Never judgmental / never the banned corporate term.
    assert "cfo" not in msg.lower()
    for banned in ("nên", "phải", "đừng"):
        assert banned not in msg.lower()


# ----- PROACTIVE_COMPANION_ENABLED flag (read at the job edge) ----------


def test_proactive_flag_default_on(monkeypatch):
    from backend.jobs import check_empathy_triggers

    monkeypatch.delenv("PROACTIVE_COMPANION_ENABLED", raising=False)
    assert check_empathy_triggers._proactive_companion_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "FALSE", "Off"])
def test_proactive_flag_off(monkeypatch, val):
    from backend.jobs import check_empathy_triggers

    monkeypatch.setenv("PROACTIVE_COMPANION_ENABLED", val)
    assert check_empathy_triggers._proactive_companion_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "anything"])
def test_proactive_flag_on(monkeypatch, val):
    from backend.jobs import check_empathy_triggers

    monkeypatch.setenv("PROACTIVE_COMPANION_ENABLED", val)
    assert check_empathy_triggers._proactive_companion_enabled() is True


# ----- #3.3 job picks up the trigger with no per-trigger wiring ---------


@pytest.mark.asyncio
async def test_job_passes_include_proactive_into_check_all_triggers(monkeypatch):
    """The hourly job feeds the flag straight into ``check_all_triggers``;
    the new trigger rides the existing dispatch with no extra wiring."""
    from backend.jobs import check_empathy_triggers

    captured = {}

    async def fake_count(*_a, **_k):
        return 0

    async def fake_check(
        db, user, *, now=None, include_proactive=True, include_activation_nudge=False
    ):
        captured["include_proactive"] = include_proactive
        return None  # short-circuits the rest of _process_user

    monkeypatch.setattr(empathy_engine, "count_empathy_fired_today", fake_count)
    monkeypatch.setattr(empathy_engine, "check_all_triggers", fake_check)
    monkeypatch.setenv("PROACTIVE_COMPANION_ENABLED", "true")

    # Stub the session factory so _process_user gets a no-op async session.
    class _Session:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(
        check_empathy_triggers, "get_session_factory", lambda: (lambda: _Session())
    )

    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=123)
    await check_empathy_triggers._process_user(user, now=NOW)

    assert captured["include_proactive"] is True


def _stub_session_factory(monkeypatch, check_empathy_triggers):
    """Make get_session_factory hand back a no-op async session."""

    class _Session:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(
        check_empathy_triggers, "get_session_factory", lambda: (lambda: _Session())
    )


@pytest.mark.asyncio
async def test_run_folds_in_onboarded_candidates_when_proactive_on(monkeypatch):
    """A recently-onboarded user with no expense is invisible to
    get_active_users but must still be scanned when the proactive flag is
    on — otherwise onboarding_no_twin_return never fires for its cohort."""
    from backend.jobs import check_empathy_triggers

    active = SimpleNamespace(id=uuid.uuid4(), telegram_id=1)
    onboarded = SimpleNamespace(id=uuid.uuid4(), telegram_id=2)

    async def fake_active(_db, **_k):
        return [active]

    async def fake_onboarded(_db, *, now):
        return [onboarded]

    scanned = []

    async def fake_process(user, *, now):
        scanned.append(user.id)

    monkeypatch.setattr(check_empathy_triggers, "get_active_users", fake_active)
    monkeypatch.setattr(
        check_empathy_triggers, "_get_onboarded_candidates", fake_onboarded
    )
    monkeypatch.setattr(check_empathy_triggers, "_process_user", fake_process)
    async def _noop_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(check_empathy_triggers.asyncio, "sleep", _noop_sleep)
    monkeypatch.setenv("PROACTIVE_COMPANION_ENABLED", "true")
    _stub_session_factory(monkeypatch, check_empathy_triggers)

    await check_empathy_triggers.run_hourly_empathy_check(now=NOW)

    assert active.id in scanned
    assert onboarded.id in scanned


@pytest.mark.asyncio
async def test_run_skips_onboarded_candidates_when_proactive_off(monkeypatch):
    """Flag off → don't even query the onboarded-only cohort."""
    from backend.jobs import check_empathy_triggers

    active = SimpleNamespace(id=uuid.uuid4(), telegram_id=1)

    async def fake_active(_db, **_k):
        return [active]

    called = {"onboarded": False}

    async def fake_onboarded(_db, *, now):
        called["onboarded"] = True
        return []

    scanned = []

    async def fake_process(user, *, now):
        scanned.append(user.id)

    monkeypatch.setattr(check_empathy_triggers, "get_active_users", fake_active)
    monkeypatch.setattr(
        check_empathy_triggers, "_get_onboarded_candidates", fake_onboarded
    )
    monkeypatch.setattr(check_empathy_triggers, "_process_user", fake_process)
    async def _noop_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(check_empathy_triggers.asyncio, "sleep", _noop_sleep)
    monkeypatch.setenv("PROACTIVE_COMPANION_ENABLED", "false")
    _stub_session_factory(monkeypatch, check_empathy_triggers)

    await check_empathy_triggers.run_hourly_empathy_check(now=NOW)

    assert called["onboarded"] is False
    assert scanned == [active.id]


@pytest.mark.asyncio
async def test_default_check_all_triggers_includes_new_trigger(monkeypatch):
    """With the default (no flag passed) the proactive trigger is in the
    dispatch list — guards against a future refactor dropping it."""
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine,
        "_check_onboarding_no_twin_return",
        _async_trigger("onboarding_no_twin_return", 3),
    )

    async def _never(*_a, **_k):
        return False

    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never)

    trigger = await empathy_engine.check_all_triggers(
        _FakeDB(), _user(days_ago_onboarded=5), now=NOW
    )
    assert trigger is not None
    assert trigger.name == "onboarding_no_twin_return"
