"""Phase 4.6 Epic 2 — Activation nudge ("chưa từng kích hoạt").

Covers the "never activated" (0 tin nhắn) cohort work:

- #2.1 the ``never_activated`` empathy trigger (fire / no-fire across the
  activation window, the onboarding + activation gates, cooldown), the
  ``include_activation_nudge`` gate on ``check_all_triggers`` (default OFF —
  the opposite of the proactive companion), and that the hourly job folds in
  the never-activated cohort + emits the ``activation_nudge_sent`` funnel
  event only for this trigger.
- #2.2 the ``activation_first_reply`` funnel: ``should_track_activation_reply``
  and the worker-edge hook in ``route_update`` that stamps a nudged user's
  first reply exactly once (excluding ``/start``, gated behind the flag).
- The ``ACTIVATION_NUDGE_ENABLED`` flag reader (default false).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.analytics import EventType
from backend.bot.personality import empathy_engine
from backend.bot.personality.empathy_engine import (
    ACTIVATION_NUDGE_MAX_DAYS,
    ACTIVATION_NUDGE_MIN_DAYS,
)

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)

# A non-None row stand-in for ``.first()`` — any truthy value signals
# "a matching row exists" to the EXISTS-style helpers.
_ROW = ("x",)


# ----- fakes ------------------------------------------------------------


class _Result:
    """Wraps one canned value across every result-accessor the engine uses."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value

    def first(self):
        return self._value

    def scalars(self):
        return self._value if self._value is not None else []


class _ScriptedDB:
    """Hands back canned results in FIFO order — one per ``execute`` call.

    The unit tests know the exact query order inside each function under
    test, so scripting the results keeps the fake tiny and precise.
    """

    def __init__(self, *results):
        self._q = list(results)

    async def execute(self, _stmt):
        assert self._q, "engine issued more queries than the test scripted"
        return _Result(self._q.pop(0))


def _user(*, completed=False, uid=None):
    return SimpleNamespace(
        id=uid or uuid.uuid4(),
        onboarding_completed_at=(NOW if completed else None),
        salutation="anh",
        get_greeting_name=lambda: "Minh",
    )


def _started(days_ago, *, naive=False):
    ts = NOW - timedelta(days=days_ago)
    return ts.replace(tzinfo=None) if naive else ts


# ----- _check_never_activated (unit) ------------------------------------


@pytest.mark.asyncio
async def test_fires_in_window_when_never_activated():
    user = _user()
    # min(bot_started) 3 days ago; no expense; no other event → activated=False.
    db = _ScriptedDB(_started(3), None, None)

    trigger = await empathy_engine._check_never_activated(db, user, NOW)

    assert trigger is not None
    assert trigger.name == "never_activated"
    assert trigger.priority == 2
    assert trigger.cooldown_days == 3
    assert trigger.context["days_since_start"] == 3


@pytest.mark.asyncio
async def test_no_fire_when_onboarding_completed():
    # Onboarded users belong to onboarding_no_twin_return, never here.
    user = _user(completed=True)
    db = _ScriptedDB()  # must not issue any query

    assert await empathy_engine._check_never_activated(db, user, NOW) is None


@pytest.mark.asyncio
async def test_no_fire_when_no_bot_started_event():
    user = _user()
    db = _ScriptedDB(None)  # min(bot_started) → None

    assert await empathy_engine._check_never_activated(db, user, NOW) is None


@pytest.mark.asyncio
async def test_no_fire_before_window_opens():
    # Opened the bot today — give them a day to reply on their own first.
    user = _user()
    db = _ScriptedDB(_started(ACTIVATION_NUDGE_MIN_DAYS - 1))

    assert await empathy_engine._check_never_activated(db, user, NOW) is None


@pytest.mark.asyncio
async def test_no_fire_after_window_closes():
    # Day 7 — the window is half-open [1, 7); silent-N-days owns it now.
    user = _user()
    db = _ScriptedDB(_started(ACTIVATION_NUDGE_MAX_DAYS))

    assert await empathy_engine._check_never_activated(db, user, NOW) is None


@pytest.mark.asyncio
async def test_no_fire_when_activated_via_expense():
    user = _user()
    # In-window, but an expense exists → _has_activated short-circuits True.
    db = _ScriptedDB(_started(3), _ROW)

    assert await empathy_engine._check_never_activated(db, user, NOW) is None


@pytest.mark.asyncio
async def test_no_fire_when_activated_via_other_event():
    user = _user()
    # No expense, but a non-nudge event exists → activated.
    db = _ScriptedDB(_started(3), None, _ROW)

    assert await empathy_engine._check_never_activated(db, user, NOW) is None


@pytest.mark.asyncio
async def test_naive_bot_started_treated_as_utc():
    user = _user()
    db = _ScriptedDB(_started(3, naive=True), None, None)

    trigger = await empathy_engine._check_never_activated(db, user, NOW)
    assert trigger is not None  # no crash comparing naive vs aware


# ----- _has_activated (unit) --------------------------------------------


@pytest.mark.asyncio
async def test_has_activated_true_on_expense():
    db = _ScriptedDB(_ROW)  # expense exists → short-circuits, no event query
    assert await empathy_engine._has_activated(db, uuid.uuid4()) is True


@pytest.mark.asyncio
async def test_has_activated_true_on_non_nudge_event():
    db = _ScriptedDB(None, _ROW)  # no expense, but a real event
    assert await empathy_engine._has_activated(db, uuid.uuid4()) is True


@pytest.mark.asyncio
async def test_has_activated_false_when_only_bot_started():
    db = _ScriptedDB(None, None)  # nothing beyond opening the bot
    assert await empathy_engine._has_activated(db, uuid.uuid4()) is False


# ----- should_track_activation_reply (unit, #2.2) -----------------------


@pytest.mark.asyncio
async def test_track_reply_true_when_nudged_and_no_reply_yet():
    db = _ScriptedDB(_ROW, None)  # nudge sent, no reply recorded
    assert await empathy_engine.should_track_activation_reply(db, uuid.uuid4()) is True


@pytest.mark.asyncio
async def test_track_reply_false_when_reply_already_recorded():
    db = _ScriptedDB(_ROW, _ROW)  # nudge sent AND reply already stamped
    assert (
        await empathy_engine.should_track_activation_reply(db, uuid.uuid4()) is False
    )


@pytest.mark.asyncio
async def test_track_reply_false_when_never_nudged():
    # No nudge → short-circuits before the reply query is ever issued.
    db = _ScriptedDB(None)
    assert (
        await empathy_engine.should_track_activation_reply(db, uuid.uuid4()) is False
    )


# ----- include_activation_nudge gate on check_all_triggers --------------


def _async_none():
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
        "_check_never_activated",
        "_check_user_silent_7_days",
        "_check_user_silent_30_days",
        "_check_weekend_high_spending",
        "_check_first_saving_month",
        "_check_consecutive_over_budget",
    ):
        monkeypatch.setattr(empathy_engine, fn_name, _async_none())


async def _never_on_cooldown(*_a, **_k):
    return False


@pytest.mark.asyncio
async def test_flag_on_activation_trigger_fires_before_silent(monkeypatch):
    _silence_all_checks(monkeypatch)
    # never_activated sits BEFORE the generic silent-7 trigger, so when both
    # match it must win — the activation window owns the early days.
    monkeypatch.setattr(
        empathy_engine, "_check_never_activated", _async_trigger("never_activated", 2)
    )
    monkeypatch.setattr(
        empathy_engine, "_check_user_silent_7_days", _async_trigger("old", 4)
    )
    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never_on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _ScriptedDB(), _user(), now=NOW, include_activation_nudge=True
    )
    assert trigger is not None
    assert trigger.name == "never_activated"


@pytest.mark.asyncio
async def test_flag_off_skips_activation_but_old_still_fires(monkeypatch):
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine, "_check_never_activated", _async_trigger("never_activated", 2)
    )
    monkeypatch.setattr(
        empathy_engine, "_check_user_silent_7_days", _async_trigger("old", 4)
    )
    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never_on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _ScriptedDB(), _user(), now=NOW, include_activation_nudge=False
    )
    assert trigger is not None
    assert trigger.name == "old"


@pytest.mark.asyncio
async def test_default_excludes_activation_trigger(monkeypatch):
    """Unlike the proactive companion (default ON), the activation nudge
    defaults OFF — omitting the kwarg must NOT fire ``never_activated``."""
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine, "_check_never_activated", _async_trigger("never_activated", 2)
    )
    monkeypatch.setattr(
        empathy_engine, "_check_user_silent_7_days", _async_trigger("old", 4)
    )
    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never_on_cooldown)

    trigger = await empathy_engine.check_all_triggers(_ScriptedDB(), _user(), now=NOW)
    assert trigger is not None
    assert trigger.name == "old"  # activation skipped by default


@pytest.mark.asyncio
async def test_cooldown_suppresses_activation_trigger(monkeypatch):
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine, "_check_never_activated", _async_trigger("never_activated", 2)
    )

    async def _on_cooldown(*_a, **_k):
        return True

    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _ScriptedDB(), _user(), now=NOW, include_activation_nudge=True
    )
    assert trigger is None


# ----- render_message: persona / localization ---------------------------


def test_render_message_threads_salutation_and_persona():
    empathy_engine.reload_messages_for_tests()
    trigger = empathy_engine.EmpathyTrigger(
        name="never_activated",
        priority=2,
        cooldown_days=3,
        context={"days_since_start": 3},
    )
    user = SimpleNamespace(salutation="anh", get_greeting_name=lambda: "Minh")

    # Both variants must satisfy the persona/localization invariants — assert
    # over a batch so a random pick can't hide a bad variant.
    for _ in range(20):
        msg = empathy_engine.render_message(trigger, user)
        assert msg.strip()
        assert "anh" in msg  # salutation threaded (name "Minh" has no "anh")
        low = msg.lower()
        # Never the banned corporate positioning terms (CLAUDE.md).
        assert "cfo" not in low
        assert "decision engine" not in low
        assert "gps" not in low
        # Bé Tiền tone guide — no scolding.
        for banned in ("đừng", "phải", "lãng phí"):
            assert banned not in low


# ----- ACTIVATION_NUDGE_ENABLED flag (read at the job/worker edge) ------


def test_activation_flag_default_off(monkeypatch):
    from backend.intent.handlers.decision_flags import is_activation_nudge_enabled

    monkeypatch.delenv("ACTIVATION_NUDGE_ENABLED", raising=False)
    assert is_activation_nudge_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "ON", "Yes"])
def test_activation_flag_on(monkeypatch, val):
    from backend.intent.handlers.decision_flags import is_activation_nudge_enabled

    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", val)
    assert is_activation_nudge_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "anything", ""])
def test_activation_flag_off(monkeypatch, val):
    from backend.intent.handlers.decision_flags import is_activation_nudge_enabled

    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", val)
    assert is_activation_nudge_enabled() is False


# ----- job wiring -------------------------------------------------------


class _JobDB:
    async def commit(self):
        return None


class _JobSession:
    async def __aenter__(self):
        return _JobDB()

    async def __aexit__(self, *_a):
        return False


def _stub_job_session(monkeypatch, check_empathy_triggers):
    monkeypatch.setattr(
        check_empathy_triggers, "get_session_factory", lambda: (lambda: _JobSession())
    )


@pytest.mark.asyncio
async def test_job_passes_include_activation_nudge(monkeypatch):
    from backend.jobs import check_empathy_triggers

    captured = {}

    async def fake_count(*_a, **_k):
        return 0

    async def fake_check(
        db,
        user,
        *,
        now=None,
        include_proactive=True,
        include_activation_nudge=False,
        include_drift=False,
    ):
        captured["include_activation_nudge"] = include_activation_nudge
        return None

    monkeypatch.setattr(empathy_engine, "count_empathy_fired_today", fake_count)
    monkeypatch.setattr(empathy_engine, "check_all_triggers", fake_check)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "true")
    _stub_job_session(monkeypatch, check_empathy_triggers)

    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=123)
    await check_empathy_triggers._process_user(user, now=NOW)

    assert captured["include_activation_nudge"] is True


async def _noop_sleep(*_a, **_k):
    return None


@pytest.mark.asyncio
async def test_run_folds_in_activation_candidates_when_on(monkeypatch):
    from backend.jobs import check_empathy_triggers

    active = SimpleNamespace(id=uuid.uuid4(), telegram_id=1)
    never = SimpleNamespace(id=uuid.uuid4(), telegram_id=2)

    async def fake_active(_db, **_k):
        return [active]

    async def fake_activation(_db, *, now):
        return [never]

    scanned = []

    async def fake_process(user, *, now):
        scanned.append(user.id)

    monkeypatch.setattr(check_empathy_triggers, "get_active_users", fake_active)
    monkeypatch.setattr(
        check_empathy_triggers, "_get_activation_candidates", fake_activation
    )
    # Keep the proactive cohort out of this test's scope.
    async def _no_onboarded(_db, *, now):
        return []

    monkeypatch.setattr(
        check_empathy_triggers, "_get_onboarded_candidates", _no_onboarded
    )
    monkeypatch.setattr(check_empathy_triggers, "_process_user", fake_process)
    monkeypatch.setattr(check_empathy_triggers.asyncio, "sleep", _noop_sleep)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "true")
    _stub_job_session(monkeypatch, check_empathy_triggers)

    await check_empathy_triggers.run_hourly_empathy_check(now=NOW)

    assert active.id in scanned
    assert never.id in scanned


@pytest.mark.asyncio
async def test_run_skips_activation_candidates_when_off(monkeypatch):
    from backend.jobs import check_empathy_triggers

    active = SimpleNamespace(id=uuid.uuid4(), telegram_id=1)

    async def fake_active(_db, **_k):
        return [active]

    called = {"activation": False}

    async def fake_activation(_db, *, now):
        called["activation"] = True
        return []

    scanned = []

    async def fake_process(user, *, now):
        scanned.append(user.id)

    monkeypatch.setattr(check_empathy_triggers, "get_active_users", fake_active)
    monkeypatch.setattr(
        check_empathy_triggers, "_get_activation_candidates", fake_activation
    )
    monkeypatch.setattr(check_empathy_triggers, "_process_user", fake_process)
    monkeypatch.setattr(check_empathy_triggers.asyncio, "sleep", _noop_sleep)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "false")
    monkeypatch.setenv("PROACTIVE_COMPANION_ENABLED", "false")
    _stub_job_session(monkeypatch, check_empathy_triggers)

    await check_empathy_triggers.run_hourly_empathy_check(now=NOW)

    assert called["activation"] is False
    assert scanned == [active.id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "trigger_name,expected_event",
    [
        ("never_activated", EventType.ACTIVATION_NUDGE_SENT),
        ("user_silent_7_days", EventType.EMPATHY_SENT),
    ],
)
async def test_process_user_funnel_event(monkeypatch, trigger_name, expected_event):
    """The activation nudge feeds ``activation_nudge_sent``; every other
    trigger stays on the generic ``empathy_sent`` stream (#2.2)."""
    from backend.jobs import check_empathy_triggers

    async def fake_count(*_a, **_k):
        return 0

    async def fake_check(db, user, **_k):
        return empathy_engine.EmpathyTrigger(
            name=trigger_name, priority=2, cooldown_days=3, context={}
        )

    async def fake_record(*_a, **_k):
        return None

    async def fake_send(**_k):
        return {"ok": True}

    tracked = []

    def fake_track(event_type, user_id=None, properties=None):
        tracked.append((event_type, user_id))

    monkeypatch.setattr(empathy_engine, "count_empathy_fired_today", fake_count)
    monkeypatch.setattr(empathy_engine, "check_all_triggers", fake_check)
    monkeypatch.setattr(empathy_engine, "render_message", lambda *a, **k: "hi")
    monkeypatch.setattr(empathy_engine, "record_fired", fake_record)
    monkeypatch.setattr(check_empathy_triggers, "send_message", fake_send)
    monkeypatch.setattr(check_empathy_triggers.analytics, "track", fake_track)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "true")
    _stub_job_session(monkeypatch, check_empathy_triggers)

    uid = uuid.uuid4()
    user = SimpleNamespace(id=uid, telegram_id=123, tone_preference=None)
    await check_empathy_triggers._process_user(user, now=NOW)

    assert (expected_event, uid) in tracked


# ----- worker #2.2 hook (route_update) ----------------------------------


class _WorkerDB:
    async def execute(self, _stmt):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _WorkerSession:
    async def __aenter__(self):
        return _WorkerDB()

    async def __aexit__(self, *_a):
        return False


def _wire_worker(monkeypatch, *, returned_user_id, should_track):
    """Patch route_update's collaborators. Returns a state dict the test
    inspects: ``track`` (calls) and ``track_checked`` (helper invoked)."""
    from backend.workers import telegram_worker
    from backend.bot.personality import empathy_engine as ee
    import backend.analytics as analytics_mod

    state = {"track": [], "track_checked": False}

    async def fake_handle_message(db, message, **_k):
        return returned_user_id

    async def fake_should_track(db, user_id):
        state["track_checked"] = True
        return should_track

    def fake_track(event_type, user_id=None, properties=None):
        state["track"].append((event_type, user_id))

    monkeypatch.setattr(telegram_worker, "_handle_message", fake_handle_message)
    monkeypatch.setattr(ee, "should_track_activation_reply", fake_should_track)
    monkeypatch.setattr(analytics_mod, "track", fake_track)
    monkeypatch.setattr(
        telegram_worker, "get_session_factory", lambda: (lambda: _WorkerSession())
    )
    return state


def _msg(text):
    return {
        "update_id": 1,
        "message": {"text": text, "chat": {"id": 5}, "from": {"id": 9}},
    }


@pytest.mark.asyncio
async def test_worker_stamps_first_reply(monkeypatch):
    from backend.workers import telegram_worker

    uid = uuid.uuid4()
    state = _wire_worker(monkeypatch, returned_user_id=uid, should_track=True)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "true")

    await telegram_worker.route_update(_msg("chào bé, mình muốn bắt đầu"))

    assert (EventType.ACTIVATION_FIRST_REPLY, uid) in state["track"]


@pytest.mark.asyncio
async def test_worker_excludes_start_command(monkeypatch):
    from backend.workers import telegram_worker

    uid = uuid.uuid4()
    state = _wire_worker(monkeypatch, returned_user_id=uid, should_track=True)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "true")

    await telegram_worker.route_update(_msg("/start"))

    # /start is the entry signal, not a reply — helper never consulted.
    assert state["track_checked"] is False
    assert not any(
        e == EventType.ACTIVATION_FIRST_REPLY for e, _ in state["track"]
    )


@pytest.mark.asyncio
async def test_worker_no_stamp_when_flag_off(monkeypatch):
    from backend.workers import telegram_worker

    uid = uuid.uuid4()
    state = _wire_worker(monkeypatch, returned_user_id=uid, should_track=True)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "false")

    await telegram_worker.route_update(_msg("chào bé"))

    assert state["track_checked"] is False
    assert state["track"] == []


@pytest.mark.asyncio
async def test_worker_no_stamp_when_helper_false(monkeypatch):
    from backend.workers import telegram_worker

    uid = uuid.uuid4()
    state = _wire_worker(monkeypatch, returned_user_id=uid, should_track=False)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "true")

    await telegram_worker.route_update(_msg("chào bé"))

    assert state["track_checked"] is True  # helper consulted…
    assert not any(  # …but said no
        e == EventType.ACTIVATION_FIRST_REPLY for e, _ in state["track"]
    )


@pytest.mark.asyncio
async def test_worker_no_stamp_for_unregistered_user(monkeypatch):
    from backend.workers import telegram_worker

    state = _wire_worker(monkeypatch, returned_user_id=None, should_track=True)
    monkeypatch.setenv("ACTIVATION_NUDGE_ENABLED", "true")

    await telegram_worker.route_update(_msg("chào bé"))

    # No resolved user → nothing to attribute, helper never consulted.
    assert state["track_checked"] is False
    assert state["track"] == []
