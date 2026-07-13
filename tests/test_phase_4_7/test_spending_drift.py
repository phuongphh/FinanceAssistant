"""Phase 4.7 Epic 1 — spending-drift warning ("nhịp chi trôi").

Covers the safe, flag-dark drift work:

- #1.1 the pure ``drift_service.assess`` math — median baseline, the dual
  (percentage AND absolute-floor) threshold, the Twin-consequence delay in
  months, and every edge that must NOT fire or must fall back to a no-delta
  variant (too little history, non-positive baseline, zero/deficit saving
  rate, sub-one-month slip).
- #1.2 the ``spending_drift`` empathy trigger: fire / no-fire and the
  ``copy_variant`` (delay / stall / plain) it hands the renderer.
- the ``include_drift`` gate on ``check_all_triggers`` (default OFF, and its
  priority slot between the acute single-transaction checks and the ambient
  silent-N-days ones).
- render_message + render_tone_variant across the nested variant dict, with
  persona / localization invariants asserted over a batch, including the
  tone-dark legacy path (the Twin delta must still render).
- the ``DRIFT_WARNING_ENABLED`` flag reader (default false) and the hourly
  job threading ``include_drift`` in.
- that a drift nudge stays on the empathy ``empathy_sent`` stream and is NOT
  logged to ``decision_query_logs`` (which would inflate the G1/G2 metrics).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.analytics import EventType
from backend.bot.personality import empathy_engine
from backend.services.decision import drift_service
from backend.services.decision.drift_service import (
    DriftAssessment,
    assess,
)

NOW_TS = empathy_engine.datetime(2026, 7, 12, 12, 0, tzinfo=empathy_engine.timezone.utc)

# 30-day-window money, all Decimal (money is never float).
_5TR = Decimal("5000000")
_3TR = Decimal("3000000")
_2TR = Decimal("2000000")
_1TR = Decimal("1000000")


# ============================================================
# drift_service.assess — pure math (#1.1)
# ============================================================


def test_assess_none_when_too_few_windows():
    # Only two baseline windows — median untrustworthy, so we never fire.
    result = assess(
        [_5TR, _5TR],
        _5TR * 3,
        goal_remaining=None,
        avg_monthly_savings=_5TR,
    )
    assert result is None


def test_assess_none_when_baseline_nonpositive():
    # Three windows but all zero → baseline 0 → no reference to drift against.
    result = assess(
        [Decimal(0), Decimal(0), Decimal(0)],
        _5TR,
        goal_remaining=None,
        avg_monthly_savings=_5TR,
    )
    assert result is None


def test_assess_takes_median_baseline():
    # Median of [4tr, 5tr, 9tr] is 5tr, NOT the 6tr mean — an outlier window
    # must not drag the baseline up and mask a real drift.
    result = assess(
        [Decimal("4000000"), _5TR, Decimal("9000000")],
        _5TR,  # current == median → no drift, but baseline is what we check
        goal_remaining=None,
        avg_monthly_savings=Decimal(0),
    )
    assert result is not None
    assert result.baseline == _5TR


def test_assess_not_drifting_below_pct():
    # +10% overshoot clears the 1tr floor but not the 20% threshold.
    result = assess(
        [Decimal("100000000")] * 3,
        Decimal("110000000"),
        goal_remaining=None,
        avg_monthly_savings=Decimal(0),
    )
    assert result is not None
    assert result.is_drifting is False


def test_assess_not_drifting_below_absolute_floor():
    # +25% clears the pct threshold, but 500k overshoot is below the 1tr floor
    # — a small-baseline user shouldn't be nudged over pocket change.
    result = assess(
        [_2TR, _2TR, _2TR],
        Decimal("2500000"),
        goal_remaining=None,
        avg_monthly_savings=Decimal(0),
    )
    assert result is not None
    assert result.drift_amount == Decimal("500000")
    assert result.is_drifting is False


def test_assess_drifting_when_both_thresholds_clear():
    result = assess(
        [_5TR, _5TR, _5TR],
        Decimal("8000000"),  # +3tr = +60%
        goal_remaining=None,
        avg_monthly_savings=Decimal(0),
    )
    assert result is not None
    assert result.is_drifting is True
    assert result.drift_amount == _3TR
    assert result.drift_pct == Decimal("0.6")


def test_assess_reports_goal_delay_months():
    # baseline 5tr, current 8tr → drift 3tr. Saving rate 5tr/mo → 2tr after
    # drift. remaining 20tr: 4 months at 5tr vs 10 months at 2tr → 6-month slip.
    result = assess(
        [_5TR, _5TR, _5TR],
        Decimal("8000000"),
        goal_remaining=Decimal("20000000"),
        avg_monthly_savings=_5TR,
        goal_label="Mua nhà",
    )
    assert result is not None
    assert result.is_drifting is True
    assert result.goal_delay_months == 6
    assert result.pace_unsustainable is False
    assert result.goal_label == "Mua nhà"


def test_assess_pace_unsustainable_when_drift_eats_whole_saving_rate():
    # drift 3tr vs saving rate 2tr → new rate negative → the goal stalls,
    # it doesn't merely slip. No month count; the copy uses the stall variant.
    result = assess(
        [_5TR, _5TR, _5TR],
        Decimal("8000000"),
        goal_remaining=Decimal("20000000"),
        avg_monthly_savings=_2TR,
        goal_label="Mua nhà",
    )
    assert result is not None
    assert result.pace_unsustainable is True
    assert result.goal_delay_months is None


def test_assess_plain_when_saving_rate_zero():
    # Saving rate floored at 0 upstream → no Twin delta to compute → plain.
    result = assess(
        [_5TR, _5TR, _5TR],
        Decimal("8000000"),
        goal_remaining=Decimal("20000000"),
        avg_monthly_savings=Decimal(0),
        goal_label="Mua nhà",
    )
    assert result is not None
    assert result.is_drifting is True
    assert result.goal_delay_months is None
    assert result.pace_unsustainable is False


def test_assess_plain_when_no_goal():
    result = assess(
        [_5TR, _5TR, _5TR],
        Decimal("8000000"),
        goal_remaining=None,
        avg_monthly_savings=_5TR,
    )
    assert result is not None
    assert result.is_drifting is True
    assert result.goal_delay_months is None
    assert result.goal_label is None


def test_assess_no_delay_reported_when_slip_under_one_month():
    # remaining 1tr: 1 month at 5tr vs 1 month at 2tr (both round up to 1) →
    # 0-month slip → not surfaced (we only nudge on a slip the user can feel).
    result = assess(
        [_5TR, _5TR, _5TR],
        Decimal("8000000"),
        goal_remaining=_1TR,
        avg_monthly_savings=_5TR,
        goal_label="Quỹ dự phòng",
    )
    assert result is not None
    assert result.is_drifting is True
    assert result.goal_delay_months is None


def test_assess_threshold_overrides_are_honoured():
    # A caller (per-user tune / test) can loosen both gates.
    result = assess(
        [_2TR, _2TR, _2TR],
        Decimal("2500000"),
        goal_remaining=None,
        avg_monthly_savings=Decimal(0),
        threshold_pct=Decimal("0.10"),
        absolute_floor=Decimal("100000"),
    )
    assert result is not None
    assert result.is_drifting is True


# ============================================================
# _spend_windows — history gate excludes internal transfers
# ============================================================


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _WindowsGateDB:
    """Fake session for ``_spend_windows``' first (MIN expense_date) query.

    It keys its answer off whether the *executed* MIN statement carries the
    internal-category exclusion: if the production code applies the filter it
    sees the user's earliest *non-internal* expense; if the filter is missing
    it sees the earlier internal-transfer row. So the gate only returns ``None``
    when the filter is really in the query — testing the fix, not the fake.
    """

    def __init__(self, *, earliest_all, earliest_noninternal):
        self.earliest_all = earliest_all
        self.earliest_noninternal = earliest_noninternal
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        sql = str(stmt).upper()
        if self.calls == 1:
            has_filter = "CATEGORY" in sql and "NOT IN" in sql
            value = self.earliest_noninternal if has_filter else self.earliest_all
            return _ScalarResult(value)
        # No further query should run once the gate short-circuits to None.
        raise AssertionError("gate should have returned before the spend query")


@pytest.mark.asyncio
async def test_spend_windows_gate_ignores_internal_transfer_history():
    # The only pre-cutoff expense is an internal transfer (day -100), but the
    # earliest genuine consumption is recent (day -50), inside the baseline
    # span — so there is NOT enough real history and the gate must return None.
    from datetime import timedelta

    from backend.services.decision.drift_service import _spend_windows

    today = NOW_TS.date()
    db = _WindowsGateDB(
        earliest_all=today - timedelta(days=100),  # transfer, before cutoff
        earliest_noninternal=today - timedelta(days=50),  # too recent
    )
    result = await _spend_windows(db, uuid.uuid4(), now=NOW_TS)
    assert result is None
    assert db.calls == 1  # short-circuited on the gate, never ran the spend query


# ============================================================
# _check_spending_drift trigger (#1.2)
# ============================================================


def _assessment(**over) -> DriftAssessment:
    base = dict(
        baseline=_5TR,
        current_spend=Decimal("8000000"),
        drift_amount=_3TR,
        drift_pct=Decimal("0.6"),
        is_drifting=True,
        goal_label=None,
        goal_delay_months=None,
        pace_unsustainable=False,
    )
    base.update(over)
    return DriftAssessment(**base)


def _patch_compute(monkeypatch, assessment):
    async def _fake(db, user, *, now=None):
        return assessment

    monkeypatch.setattr(drift_service, "compute_drift", _fake)


def _drift_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        salutation="anh",
        get_greeting_name=lambda: "Minh",
    )


@pytest.mark.asyncio
async def test_check_drift_no_fire_when_none(monkeypatch):
    _patch_compute(monkeypatch, None)
    assert (
        await empathy_engine._check_spending_drift(None, _drift_user(), NOW_TS) is None
    )


@pytest.mark.asyncio
async def test_check_drift_no_fire_when_not_drifting(monkeypatch):
    _patch_compute(monkeypatch, _assessment(is_drifting=False))
    assert (
        await empathy_engine._check_spending_drift(None, _drift_user(), NOW_TS) is None
    )


@pytest.mark.asyncio
async def test_check_drift_delay_variant(monkeypatch):
    _patch_compute(
        monkeypatch,
        _assessment(goal_label="Mua nhà", goal_delay_months=6),
    )
    trigger = await empathy_engine._check_spending_drift(None, _drift_user(), NOW_TS)
    assert trigger is not None
    assert trigger.name == "spending_drift"
    assert trigger.priority == 3
    assert trigger.cooldown_days == empathy_engine.SPENDING_DRIFT_COOLDOWN_DAYS == 14
    assert trigger.context["copy_variant"] == "delay"
    assert trigger.context["goal_label"] == "Mua nhà"
    assert trigger.context["goal_delay_months"] == 6
    # drift amount is pre-formatted currency, not a raw Decimal.
    assert "đ" in trigger.context["drift"]


@pytest.mark.asyncio
async def test_check_drift_stall_variant(monkeypatch):
    _patch_compute(
        monkeypatch,
        _assessment(goal_label="Mua nhà", pace_unsustainable=True),
    )
    trigger = await empathy_engine._check_spending_drift(None, _drift_user(), NOW_TS)
    assert trigger is not None
    assert trigger.context["copy_variant"] == "stall"
    assert trigger.context["goal_label"] == "Mua nhà"
    assert "goal_delay_months" not in trigger.context


@pytest.mark.asyncio
async def test_check_drift_plain_variant_when_no_goal(monkeypatch):
    _patch_compute(monkeypatch, _assessment())  # no goal_label
    trigger = await empathy_engine._check_spending_drift(None, _drift_user(), NOW_TS)
    assert trigger is not None
    assert trigger.context["copy_variant"] == "plain"
    assert "goal_label" not in trigger.context


@pytest.mark.asyncio
async def test_check_drift_plain_when_delay_but_no_goal_label(monkeypatch):
    # A delay figure with no goal label can't name a goal → plain, never a
    # half-rendered "{goal_label}" placeholder.
    _patch_compute(monkeypatch, _assessment(goal_delay_months=6, goal_label=None))
    trigger = await empathy_engine._check_spending_drift(None, _drift_user(), NOW_TS)
    assert trigger is not None
    assert trigger.context["copy_variant"] == "plain"


@pytest.mark.asyncio
async def test_check_drift_html_escapes_goal_label(monkeypatch):
    # The hourly job sends drift messages with parse_mode="HTML", so a
    # user-authored goal name with HTML metacharacters must be escaped before
    # it reaches the render context — otherwise it breaks Telegram's HTML
    # parse (or injects markup).
    _patch_compute(
        monkeypatch,
        _assessment(goal_label="Mua <nhà> & xe", goal_delay_months=6),
    )
    trigger = await empathy_engine._check_spending_drift(None, _drift_user(), NOW_TS)
    assert trigger is not None
    assert trigger.context["copy_variant"] == "delay"
    assert trigger.context["goal_label"] == "Mua &lt;nhà&gt; &amp; xe"
    assert "<" not in trigger.context["goal_label"]


@pytest.mark.asyncio
async def test_check_drift_html_escapes_goal_label_in_stall(monkeypatch):
    # Same escaping guarantee on the stall variant path.
    _patch_compute(
        monkeypatch,
        _assessment(goal_label="Quỹ <dự phòng>", pace_unsustainable=True),
    )
    trigger = await empathy_engine._check_spending_drift(None, _drift_user(), NOW_TS)
    assert trigger is not None
    assert trigger.context["copy_variant"] == "stall"
    assert trigger.context["goal_label"] == "Quỹ &lt;dự phòng&gt;"


# ============================================================
# include_drift gate on check_all_triggers
# ============================================================


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
        "_check_spending_drift",
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


class _EmptyDB:
    async def execute(self, _stmt):  # pragma: no cover - never reached
        raise AssertionError("no query expected when checks are stubbed")


@pytest.mark.asyncio
async def test_flag_on_drift_fires_before_silent(monkeypatch):
    _silence_all_checks(monkeypatch)
    # Drift sits BEFORE the ambient silent-N-days nudges — a concrete goal
    # consequence outranks a generic "come back".
    monkeypatch.setattr(
        empathy_engine, "_check_spending_drift", _async_trigger("spending_drift", 3)
    )
    monkeypatch.setattr(
        empathy_engine, "_check_user_silent_7_days", _async_trigger("old", 4)
    )
    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never_on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _EmptyDB(), _drift_user(), now=NOW_TS, include_drift=True
    )
    assert trigger is not None
    assert trigger.name == "spending_drift"


@pytest.mark.asyncio
async def test_flag_on_drift_yields_to_acute_large_transaction(monkeypatch):
    _silence_all_checks(monkeypatch)
    # An acute single-transaction signal still outranks the slow drift signal.
    monkeypatch.setattr(
        empathy_engine, "_check_large_transaction", _async_trigger("large", 1)
    )
    monkeypatch.setattr(
        empathy_engine, "_check_spending_drift", _async_trigger("spending_drift", 3)
    )
    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never_on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _EmptyDB(), _drift_user(), now=NOW_TS, include_drift=True
    )
    assert trigger is not None
    assert trigger.name == "large"


@pytest.mark.asyncio
async def test_flag_off_skips_drift_but_silent_still_fires(monkeypatch):
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine, "_check_spending_drift", _async_trigger("spending_drift", 3)
    )
    monkeypatch.setattr(
        empathy_engine, "_check_user_silent_7_days", _async_trigger("old", 4)
    )
    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never_on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _EmptyDB(), _drift_user(), now=NOW_TS, include_drift=False
    )
    assert trigger is not None
    assert trigger.name == "old"


@pytest.mark.asyncio
async def test_default_excludes_drift_trigger(monkeypatch):
    """Drift defaults OFF — omitting the kwarg must NOT fire ``spending_drift``."""
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine, "_check_spending_drift", _async_trigger("spending_drift", 3)
    )
    monkeypatch.setattr(
        empathy_engine, "_check_user_silent_7_days", _async_trigger("old", 4)
    )
    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _never_on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _EmptyDB(), _drift_user(), now=NOW_TS
    )
    assert trigger is not None
    assert trigger.name == "old"


@pytest.mark.asyncio
async def test_cooldown_suppresses_drift(monkeypatch):
    _silence_all_checks(monkeypatch)
    monkeypatch.setattr(
        empathy_engine, "_check_spending_drift", _async_trigger("spending_drift", 3)
    )

    async def _on_cooldown(*_a, **_k):
        return True

    monkeypatch.setattr(empathy_engine, "_is_on_cooldown", _on_cooldown)

    trigger = await empathy_engine.check_all_triggers(
        _EmptyDB(), _drift_user(), now=NOW_TS, include_drift=True
    )
    assert trigger is None


# ============================================================
# render_message — legacy (tone-dark) path across variants
# ============================================================

_BANNED_SCOLD = ("đừng", "không nên", "phải", "sai", "tệ", "lãng phí")
_BANNED_CORPORATE = ("cfo", "decision engine", "gps")


def _assert_persona(msg: str) -> None:
    assert msg.strip()
    low = msg.lower()
    for term in _BANNED_CORPORATE:
        assert term not in low, f"corporate term {term!r} leaked into copy"
    for term in _BANNED_SCOLD:
        assert term not in low, f"scolding term {term!r} leaked into copy"


def _trigger(copy_variant, **ctx):
    context = {"drift": "3,000,000đ", "copy_variant": copy_variant, **ctx}
    return empathy_engine.EmpathyTrigger(
        name="spending_drift",
        priority=3,
        cooldown_days=14,
        context=context,
    )


def test_render_delay_variant_legacy_shows_twin_delta():
    empathy_engine.reload_messages_for_tests()
    user = SimpleNamespace(salutation="anh", get_greeting_name=lambda: "Minh")
    trigger = _trigger("delay", goal_label="Mua nhà", goal_delay_months=6)

    for _ in range(20):
        msg = empathy_engine.render_message(trigger, user)  # tone dark
        _assert_persona(msg)
        assert "anh" in msg  # salutation threaded
        assert "Mua nhà" in msg  # goal named
        assert "6" in msg  # the Twin delta renders even with the dial dark
        assert "3,000,000đ" in msg  # drift amount rendered
        assert "{" not in msg  # no dangling placeholder


def test_render_stall_variant_legacy():
    empathy_engine.reload_messages_for_tests()
    user = SimpleNamespace(salutation="chị", get_greeting_name=lambda: "Lan")
    trigger = _trigger("stall", goal_label="Mua nhà")

    for _ in range(20):
        msg = empathy_engine.render_message(trigger, user)
        _assert_persona(msg)
        assert "chị" in msg
        assert "Mua nhà" in msg
        assert "{" not in msg


def test_render_plain_variant_legacy():
    empathy_engine.reload_messages_for_tests()
    user = SimpleNamespace(salutation="bạn", get_greeting_name=lambda: "Anh")
    trigger = _trigger("plain")

    for _ in range(20):
        msg = empathy_engine.render_message(trigger, user)
        _assert_persona(msg)
        assert "3,000,000đ" in msg
        assert "{" not in msg


# ============================================================
# render_tone_variant — nested variant dict (gentle / strict)
# ============================================================

from backend.bot.formatters import tone as tone_mod  # noqa: E402


@pytest.mark.parametrize("tone", ["gentle", "strict"])
def test_tone_variant_delay_renders(tone):
    tone_mod._tone_copy.cache_clear()
    for _ in range(10):
        out = tone_mod.render_tone_variant(
            "empathy.spending_drift",
            tone,
            salutation="anh",
            copy_variant="delay",
            drift="3,000,000đ",
            goal_label="Mua nhà",
            goal_delay_months=6,
        )
        assert out is not None
        _assert_persona(out)
        assert "anh" in out
        assert "Mua nhà" in out
        assert "6" in out
        assert "{" not in out


@pytest.mark.parametrize("tone", ["gentle", "strict"])
def test_tone_variant_stall_renders(tone):
    tone_mod._tone_copy.cache_clear()
    out = tone_mod.render_tone_variant(
        "empathy.spending_drift",
        tone,
        salutation="anh",
        copy_variant="stall",
        drift="3,000,000đ",
        goal_label="Mua nhà",
    )
    assert out is not None
    _assert_persona(out)
    assert "{" not in out


@pytest.mark.parametrize("tone", ["gentle", "strict"])
def test_tone_variant_plain_renders(tone):
    tone_mod._tone_copy.cache_clear()
    out = tone_mod.render_tone_variant(
        "empathy.spending_drift",
        tone,
        salutation="anh",
        copy_variant="plain",
        drift="3,000,000đ",
    )
    assert out is not None
    _assert_persona(out)
    assert "{" not in out


def test_tone_variant_none_for_unknown_copy_variant():
    # A nested block with an unmatched branch falls back (None) so the caller
    # keeps its legacy copy rather than rendering an empty string.
    tone_mod._tone_copy.cache_clear()
    out = tone_mod.render_tone_variant(
        "empathy.spending_drift",
        "gentle",
        salutation="anh",
        copy_variant="does-not-exist",
        drift="3,000,000đ",
    )
    assert out is None


def test_tone_variant_dark_returns_none():
    # tone=None (dial dark) always yields None → caller uses legacy copy.
    assert (
        tone_mod.render_tone_variant(
            "empathy.spending_drift",
            None,
            salutation="anh",
            copy_variant="plain",
            drift="3,000,000đ",
        )
        is None
    )


# ============================================================
# DRIFT_WARNING_ENABLED flag (read at the job edge)
# ============================================================


def test_drift_flag_default_off(monkeypatch):
    from backend.intent.handlers.decision_flags import is_drift_warning_enabled

    monkeypatch.delenv("DRIFT_WARNING_ENABLED", raising=False)
    assert is_drift_warning_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "ON", "Yes"])
def test_drift_flag_on(monkeypatch, val):
    from backend.intent.handlers.decision_flags import is_drift_warning_enabled

    monkeypatch.setenv("DRIFT_WARNING_ENABLED", val)
    assert is_drift_warning_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "anything", ""])
def test_drift_flag_off(monkeypatch, val):
    from backend.intent.handlers.decision_flags import is_drift_warning_enabled

    monkeypatch.setenv("DRIFT_WARNING_ENABLED", val)
    assert is_drift_warning_enabled() is False


# ============================================================
# job wiring — the hourly job threads include_drift in
# ============================================================


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
        check_empathy_triggers, "get_session_factory", lambda: lambda: _JobSession()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("flag,expected", [("true", True), ("false", False)])
async def test_job_passes_include_drift(monkeypatch, flag, expected):
    from backend.jobs import check_empathy_triggers

    captured = {}

    async def fake_count(*_a, **_k):
        return 0

    async def fake_check(db, user, **kwargs):
        captured["include_drift"] = kwargs.get("include_drift")
        return None

    monkeypatch.setattr(empathy_engine, "count_empathy_fired_today", fake_count)
    monkeypatch.setattr(empathy_engine, "check_all_triggers", fake_check)
    monkeypatch.setenv("DRIFT_WARNING_ENABLED", flag)
    _stub_job_session(monkeypatch, check_empathy_triggers)

    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=123, tone_preference=None)
    await check_empathy_triggers._process_user(user, now=NOW_TS)

    assert captured["include_drift"] is expected


# ============================================================
# drift stays on the empathy stream — NOT decision_query_logs
# ============================================================


@pytest.mark.asyncio
async def test_drift_nudge_uses_empathy_stream_not_decision_log(monkeypatch):
    """A drift nudge stamps the generic ``empathy_sent`` event and records an
    ``empathy_fired`` cooldown row — it must NOT write ``decision_query_logs``
    (that table feeds the G1/G2 adoption metrics, which a proactive nudge would
    inflate — see ``decision_query_log`` module note)."""
    from backend.jobs import check_empathy_triggers

    async def fake_count(*_a, **_k):
        return 0

    async def fake_check(db, user, **_k):
        return empathy_engine.EmpathyTrigger(
            name="spending_drift", priority=3, cooldown_days=14, context={}
        )

    recorded = []

    async def fake_record(db, user_id, trigger_name, **_k):
        recorded.append(trigger_name)

    async def fake_send(**_k):
        return {"ok": True}

    tracked = []

    def fake_track(event_type, user_id=None, properties=None):
        tracked.append(event_type)

    monkeypatch.setattr(empathy_engine, "count_empathy_fired_today", fake_count)
    monkeypatch.setattr(empathy_engine, "check_all_triggers", fake_check)
    monkeypatch.setattr(empathy_engine, "render_message", lambda *a, **k: "nhịp chi")
    monkeypatch.setattr(empathy_engine, "record_fired", fake_record)
    monkeypatch.setattr(check_empathy_triggers, "send_message", fake_send)
    monkeypatch.setattr(check_empathy_triggers.analytics, "track", fake_track)
    monkeypatch.setenv("DRIFT_WARNING_ENABLED", "true")
    _stub_job_session(monkeypatch, check_empathy_triggers)

    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=123, tone_preference=None)
    await check_empathy_triggers._process_user(user, now=NOW_TS)

    # Cooldown row stamped on the empathy stream, funnel event is the generic
    # EMPATHY_SENT — never the activation funnel, never a decision-log write.
    assert recorded == ["spending_drift"]
    assert tracked == [EventType.EMPATHY_SENT]


def test_no_drift_query_type_exists():
    """Guard: drift must have no ``decision_query_logs`` query_type — the only
    Phase 4.7 addition to that table is the user-initiated scam check."""
    from backend.models import decision_query_log as dql

    for value in dql.VALID_QUERY_TYPES:
        assert "drift" not in value.lower()
    assert dql.QUERY_TYPE_SCAM_CHECK == "scam_check"
