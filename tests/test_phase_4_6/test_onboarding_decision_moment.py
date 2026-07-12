"""Phase 4.6 Epic 3 — Decision Moment in onboarding.

Right after the Twin reveal, Bé Tiền poses ONE goal-specific decision question
and answers it on the spot with **exactly one** number, then tells the truth
about how sharp the picture is (độ nét). It reuses the Phase 4.5 services
(``plan_feasibility_service`` + ``clarity_service``) — no new engine — behind
the ``ONBOARDING_DECISION_MOMENT_ENABLED`` flag (default off).

This suite locks the invariants that matter for the 22-35 / Level 0→1 segment:

* **flag** — reads env truthy/falsy exactly like the sibling onboarding flags,
  and is off by default so the reveal stays byte-identical to pre-4.6.
* **config** — every reset goal resolves a question + typical milestone; an
  unknown / legacy goal falls back to ``default_goal`` so the moment never
  strands a user at a dead end. Money is a ``Decimal`` (layer contract).
* **answer shapes** — the three honest shapes (on_track / building / direction)
  are picked from how much the feasibility engine could conclude, and thin data
  (the common onboarding case) pivots to a directional milestone, never a "no".
* **độ nét** — the clarity line is always appended; below threshold it is
  humble, above it nudges with the single highest-leverage thing to add.
* **copy hygiene** — no forbidden positioning terms and no harsh tone words leak
  into any user-facing string.
* **handler** — ``_send_decision_moment`` sends question + answer, logs one
  append-only feasibility row with the clarity score, and is best-effort so a
  failure can never break the Twin reveal.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.bot.formatters import onboarding_decision
from backend.models.onboarding_session import RESET_GOALS
from backend.services.decision.clarity_service import (
    CLARITY_MIN_THRESHOLD,
    ClarityInputs,
    score_clarity,
)
from backend.services.decision.plan_feasibility_service import assess


# forbidden user-facing positioning terms (CLAUDE.md — never in decision copy)
_FORBIDDEN_TERMS = ("decision engine", "gps tài chính", "cfo", "personal cfo")

# harsh / shaming tone words banned by the Bé Tiền persona guide.
_BANNED_TONE = ("đừng", "không nên", "phải", "sai", "tệ", "lãng phí")

_NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def _user(salutation: str = "bạn"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        display_name="Minh",
        salutation=salutation,
    )


class _FakeSavepoint:
    """Async-CM stand-in for ``AsyncSession.begin_nested()`` — the handler wraps
    its best-effort DB work in a SAVEPOINT, so the fake session must yield one.
    Propagates exceptions (returns False) exactly like the real savepoint."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Minimal ``AsyncSession`` duck for the handler tests — the DB reads/writes
    are all monkeypatched, so the only method the handler calls on it directly is
    ``begin_nested()``."""

    def begin_nested(self):
        return _FakeSavepoint()


def _clarity(
    *,
    assets: int = 0,
    types: int = 0,
    fresh_days: int | None = None,
    income: int = 0,
    expense_months: int = 0,
    goals: int = 0,
):
    """Build a real :class:`ClarityResult` from raw signals via the pure core."""
    latest = None if fresh_days is None else _NOW - timedelta(days=fresh_days)
    return score_clarity(
        ClarityInputs(
            active_asset_count=assets,
            distinct_asset_types=types,
            latest_asset_valued_at=latest,
            income_source_count=income,
            expense_month_count=expense_months,
            active_goal_count=goals,
            now=_NOW,
        )
    )


# ----- flag: read at the edge, off by default ------------------------------


def test_flag_helper_reads_env_truthy_and_falsy(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    for on in ("1", "true", "yes", "on", "TRUE", "On"):
        monkeypatch.setenv(onboarding_v2.ONBOARDING_DECISION_MOMENT_FLAG_ENV, on)
        assert onboarding_v2.is_onboarding_decision_moment_enabled() is True, on
    for off in ("0", "false", "no", "off", ""):
        monkeypatch.setenv(onboarding_v2.ONBOARDING_DECISION_MOMENT_FLAG_ENV, off)
        assert onboarding_v2.is_onboarding_decision_moment_enabled() is False, off
    monkeypatch.delenv(
        onboarding_v2.ONBOARDING_DECISION_MOMENT_FLAG_ENV, raising=False
    )
    assert onboarding_v2.is_onboarding_decision_moment_enabled() is False


# ----- config: every goal resolves; unknown falls back ---------------------


def test_goal_config_resolves_every_reset_goal():
    for code in RESET_GOALS:
        cfg = onboarding_decision.goal_config(code)
        assert cfg.question.strip()
        assert cfg.goal_label.strip()
        assert cfg.target_vnd > 0
        assert cfg.horizon_years > 0
        # Money is Decimal (layer contract), not the raw int/float from YAML.
        assert isinstance(cfg.target_vnd, Decimal)
        assert isinstance(cfg.horizon_years, Decimal)


def test_goal_config_reset_goals_have_distinct_milestones():
    """Each reset goal points at its own typical milestone — a shared fallback
    number would make the moment feel canned."""
    targets = {code: onboarding_decision.goal_config(code).target_vnd for code in RESET_GOALS}
    assert len(set(targets.values())) == len(RESET_GOALS), targets


@pytest.mark.parametrize("code", [None, "understand_wealth", "no_such_goal", ""])
def test_goal_config_falls_back_to_default_for_unknown(code):
    """Legacy / unknown / empty codes still get a question — the default goal."""
    cfg = onboarding_decision.goal_config(code)
    default = onboarding_decision.goal_config("definitely_not_a_goal_code")
    assert cfg == default
    assert cfg.question.strip()
    assert cfg.target_vnd == Decimal("100000000")


# ----- question: threads salutation, no stray placeholder ------------------


@pytest.mark.parametrize("code", list(RESET_GOALS) + [None])
@pytest.mark.parametrize("salutation", ["anh", "chị", "bạn"])
def test_render_question_threads_salutation(code, salutation):
    cfg = onboarding_decision.goal_config(code)
    q = onboarding_decision.render_question(cfg, salutation=salutation)
    assert salutation in q
    assert "{" not in q and "}" not in q  # no unfilled placeholder


# ----- answer: three honest shapes, always one number ----------------------


def test_answer_already_reached_celebrates_without_a_countdown():
    cfg = onboarding_decision.goal_config("emergency_fund")
    # Start already at/above target → already_reached shape.
    result = assess(cfg.target_vnd, cfg.target_vnd, cfg.horizon_years, Decimal(0))
    assert result.already_reached
    text = onboarding_decision.render_answer(result, cfg, _clarity(), salutation="anh")
    assert "anh" in text
    # ``months`` is the horizon fallback here — must NOT be phrased as a
    # remaining countdown ("còn X tháng") for someone who is already there.
    assert f"{result.months} tháng" not in text
    assert "{" not in text and "}" not in text


def test_answer_on_track_when_band_achievable():
    cfg = onboarding_decision.goal_config("emergency_fund")
    # Small gap, strong saving rate → EASY/FEASIBLE → on_track (months).
    result = assess(
        Decimal("50000000"), cfg.target_vnd, cfg.horizon_years, Decimal("5000000")
    )
    assert result.band in ("easy", "feasible")
    text = onboarding_decision.render_answer(result, cfg, _clarity(), salutation="bạn")
    assert str(result.months) in text


def test_answer_building_when_saving_but_short():
    cfg = onboarding_decision.goal_config("first_home")
    # Some saving rate, still a long reach → building shape (reachable target).
    result = assess(Decimal(0), cfg.target_vnd, cfg.horizon_years, Decimal("1000000"))
    assert result.actual_monthly_savings > 0
    assert result.reachable_target is not None
    from backend.bot.formatters.money import format_money_short

    text = onboarding_decision.render_answer(result, cfg, _clarity(), salutation="chị")
    assert format_money_short(result.reachable_target) in text
    # Exactly one goal number: the reachable amount. The real milestone lives in
    # the question, so it must NOT be repeated here (keeps the one-number promise).
    assert format_money_short(cfg.target_vnd) not in text


def test_answer_direction_when_no_saving_signal():
    """The common onboarding case: no saving-rate data → UNKNOWN band → point
    at the milestone framed as a start, never a flat 'no'."""
    cfg = onboarding_decision.goal_config("wedding")
    result = assess(Decimal(0), cfg.target_vnd, cfg.horizon_years, Decimal(0))
    assert result.actual_monthly_savings == 0
    from backend.bot.formatters.money import format_money_short

    text = onboarding_decision.render_answer(result, cfg, _clarity(), salutation="bạn")
    assert format_money_short(cfg.target_vnd) in text
    # No invented timeline — direction copy never states a month count as fact.
    assert "{" not in text and "}" not in text


# ----- độ nét: always appended, humble below threshold ---------------------


def test_clarity_line_below_threshold_is_humble_and_suggests_sharpen():
    cfg = onboarding_decision.goal_config("emergency_fund")
    result = assess(Decimal(0), cfg.target_vnd, cfg.horizon_years, Decimal(0))
    clarity = _clarity()  # all zero → score 0, below threshold
    assert clarity.is_below_threshold
    text = onboarding_decision.render_answer(result, cfg, clarity, salutation="bạn")

    copy = onboarding_decision._decision_copy()["clarity"]
    top = clarity.top_sharpen()
    sharpen_text = copy["sharpen"][top.key]
    assert str(clarity.score) in text
    assert sharpen_text in text


def test_clarity_line_above_threshold_nudges_with_sharpen_tail():
    cfg = onboarding_decision.goal_config("emergency_fund")
    result = assess(Decimal(0), cfg.target_vnd, cfg.horizon_years, Decimal(0))
    # One fresh asset → score ~35, above threshold but still sharpenable.
    clarity = _clarity(assets=1, types=1, fresh_days=5)
    assert not clarity.is_below_threshold
    assert clarity.score >= CLARITY_MIN_THRESHOLD
    text = onboarding_decision.render_answer(result, cfg, clarity, salutation="bạn")

    copy = onboarding_decision._decision_copy()["clarity"]
    top = clarity.top_sharpen()
    assert str(clarity.score) in text
    assert copy["sharpen"][top.key] in text


def test_clarity_sharpen_suggestion_tracks_the_missing_component():
    """The sharpen nudge names the single highest-leverage missing dimension —
    here assets+freshness are complete, so it should point at income."""
    cfg = onboarding_decision.goal_config("emergency_fund")
    result = assess(Decimal(0), cfg.target_vnd, cfg.horizon_years, Decimal(0))
    clarity = _clarity(assets=3, types=3, fresh_days=5)  # assets+freshness maxed
    top = clarity.top_sharpen()
    assert top.key == "income"
    text = onboarding_decision.render_answer(result, cfg, clarity, salutation="bạn")
    copy = onboarding_decision._decision_copy()["clarity"]
    assert copy["sharpen"]["income"] in text


# ----- copy hygiene: no forbidden positioning / harsh tone -----------------


def _all_copy_strings() -> str:
    return str(onboarding_decision._decision_copy()).lower()


def test_copy_has_no_forbidden_positioning_terms():
    blob = _all_copy_strings()
    for banned in _FORBIDDEN_TERMS:
        assert banned not in blob, f"forbidden term leaked: {banned!r}"


def test_copy_has_no_harsh_tone_words():
    blob = _all_copy_strings()
    for banned in _BANNED_TONE:
        assert banned not in blob, f"harsh tone word leaked: {banned!r}"


# ----- handler: _send_decision_moment wiring -------------------------------


@pytest.mark.asyncio
async def test_send_decision_moment_sends_question_answer_and_logs(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.services.decision import (
        clarity_service,
        decision_query_log_service,
    )
    from backend.services.goal_projection import get_avg_monthly_savings  # noqa: F401
    from backend.services import goal_projection
    from backend.services.onboarding import onboarding_service

    user = _user(salutation="anh")

    async def _get_session(_db, _uid):
        return SimpleNamespace(
            goal_choice="emergency_fund",
            first_asset_value_vnd=Decimal("10000000"),
        )

    async def _avg_savings(_db, _uid, **_k):
        return Decimal(0)

    async def _compute_clarity(_db, _uid, **_k):
        return _clarity(assets=1, types=1, fresh_days=5)

    sent: list[str] = []

    async def _send(chat_id, text, **kwargs):
        sent.append(text)
        return {"result": {"message_id": len(sent)}}

    logged: list[dict] = []

    async def _log_query(_db, **kwargs):
        logged.append(kwargs)

    monkeypatch.setattr(onboarding_service, "get_session", _get_session)
    monkeypatch.setattr(goal_projection, "get_avg_monthly_savings", _avg_savings)
    monkeypatch.setattr(clarity_service, "compute_clarity", _compute_clarity)
    monkeypatch.setattr(decision_query_log_service, "log_query", _log_query)
    tracked: list[tuple] = []

    def _track(event, **kwargs):
        tracked.append((event, kwargs))

    monkeypatch.setattr(onboarding_v2, "send_message", _send)
    monkeypatch.setattr(onboarding_v2.analytics, "track", _track)

    await onboarding_v2._send_decision_moment(_FakeSession(), chat_id=42, user=user)

    # Exactly the question then the answer, both in the user's salutation.
    assert len(sent) == 2
    assert all("anh" in msg for msg in sent)
    # One append-only feasibility row carrying the độ nét through to E4.
    assert len(logged) == 1
    from backend.models.decision_query_log import QUERY_TYPE_FEASIBILITY

    assert logged[0]["query_type"] == QUERY_TYPE_FEASIBILITY
    assert logged[0]["success"] is True
    assert logged[0]["clarity_score"] == _clarity(assets=1, types=1, fresh_days=5).score
    # Analytics fired past the band read — guards the str-vs-enum band bug so a
    # regression there can't be silently swallowed by the best-effort wrapper.
    assert len(tracked) == 1
    assert tracked[0][0] == "onboarding_decision_moment_shown"
    assert tracked[0][1]["properties"]["band"] == "unknown"


@pytest.mark.asyncio
async def test_send_decision_moment_noop_without_session(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.services.onboarding import onboarding_service

    async def _get_session(_db, _uid):
        return None

    sent: list[str] = []

    async def _send(chat_id, text, **kwargs):
        sent.append(text)

    monkeypatch.setattr(onboarding_service, "get_session", _get_session)
    monkeypatch.setattr(onboarding_v2, "send_message", _send)
    monkeypatch.setattr(onboarding_v2.analytics, "track", lambda *a, **k: None)

    await onboarding_v2._send_decision_moment(_FakeSession(), chat_id=42, user=_user())
    assert sent == []


@pytest.mark.asyncio
async def test_send_decision_moment_is_best_effort(monkeypatch):
    """A failure inside the moment must be swallowed — the Twin reveal already
    happened and must never be broken by this add-on."""
    from backend.bot.handlers import onboarding_v2
    from backend.services.onboarding import onboarding_service

    async def _boom(_db, _uid):
        raise RuntimeError("db blew up")

    monkeypatch.setattr(onboarding_service, "get_session", _boom)
    monkeypatch.setattr(onboarding_v2, "send_message", lambda *a, **k: None)
    monkeypatch.setattr(onboarding_v2.analytics, "track", lambda *a, **k: None)

    # Must not raise — the savepoint rolls back and the wrapper swallows.
    await onboarding_v2._send_decision_moment(_FakeSession(), chat_id=42, user=_user())
