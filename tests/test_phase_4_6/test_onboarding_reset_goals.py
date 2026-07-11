"""Phase 4.6 Epic 1 — Onboarding goal reset for the 22-35 / Level 0→1 segment.

The v2 goal question framed everything as asset management ("hiểu rõ tổng tài
sản của tôi"), which does not speak to someone still building their first
savings. The reset flow swaps in first-life milestones (quỹ khẩn cấp / mua nhà
đầu tiên / cưới) behind the ``ONBOARDING_RESET_ENABLED`` flag (default off).

This suite locks four invariants:

* **model** — the new goal codes join ``ALL_GOALS`` without displacing the
  legacy set, ``understand_wealth`` stays first (downstream fallbacks depend on
  it), the codes fit ``goal_choice`` (``String(32)``) and are re-exported.
* **content** — ``step_1_goal_reset`` has aligned order/buttons/goal_acks, no
  forbidden user-facing terms leak, and the legacy ``step_1_goal`` is untouched.
* **next_action** — every reset goal resolves a CTA in all three asset states,
  and an unknown goal still falls back to the ``understand_wealth`` cell.
* **handler** — the flag drives ``_goal_step_copy`` to pick the reset vs legacy
  block, ``_send_goal_question`` builds the keyboard from the content ``order``
  list, and ``_on_goal_picked`` renders the reset ack + accepts the new codes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest


# forbidden user-facing positioning terms (CLAUDE.md — never in reset copy)
_FORBIDDEN_TERMS = ("decision engine", "gps tài chính", "cfo", "personal cfo")


def _user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        display_name="Minh",
        wizard_state={"flow": "onboarding"},
    )


# ----- model: goal-code registry -----------------------------------------


def test_reset_goals_join_all_goals_without_displacing_legacy():
    from backend.models.onboarding_session import (
        ALL_GOALS,
        LEGACY_GOALS,
        RESET_GOALS,
    )

    # Both sets are present and disjoint — no accidental overlap.
    assert set(RESET_GOALS).issubset(set(ALL_GOALS))
    assert set(LEGACY_GOALS).issubset(set(ALL_GOALS))
    assert set(LEGACY_GOALS).isdisjoint(set(RESET_GOALS))
    assert set(ALL_GOALS) == set(LEGACY_GOALS) | set(RESET_GOALS)


def test_understand_wealth_stays_first_for_fallbacks():
    """``next(iter(ALL_GOALS))`` and the next_action fallback both assume the
    default goal is ``understand_wealth`` — a reorder would silently change the
    CTA shown to users with an unknown goal."""
    from backend.models.onboarding_session import (
        ALL_GOALS,
        GOAL_UNDERSTAND_WEALTH,
    )

    assert ALL_GOALS[0] == GOAL_UNDERSTAND_WEALTH
    assert next(iter(ALL_GOALS)) == GOAL_UNDERSTAND_WEALTH


def test_reset_goal_codes_fit_goal_choice_column():
    """``goal_choice`` is ``String(32)``; a longer code would truncate/raise."""
    from backend.models.onboarding_session import RESET_GOALS

    for code in RESET_GOALS:
        assert len(code) <= 32, code


def test_goal_choice_column_is_string_32():
    from backend.models.onboarding_session import OnboardingSession

    col = OnboardingSession.__table__.c.goal_choice
    assert col.type.length == 32


def test_reset_goal_codes_reexported_from_models_package():
    import backend.models as models

    for name in (
        "GOAL_EMERGENCY_FUND",
        "GOAL_FIRST_HOME",
        "GOAL_WEDDING",
        "LEGACY_GOALS",
        "RESET_GOALS",
    ):
        assert name in models.__all__, name
        assert hasattr(models, name), name


# ----- content: step_1_goal_reset block -----------------------------------


def _load_copy():
    from backend.services.onboarding import onboarding_service

    return onboarding_service.load_copy()


def test_reset_block_order_buttons_acks_aligned():
    from backend.models.onboarding_session import RESET_GOALS

    step = _load_copy()["step_1_goal_reset"]
    order = step["order"]
    buttons = step["buttons"]
    acks = step["goal_acks"]

    # The reset block advertises exactly the RESET_GOALS codes, in a stable
    # order, with a button label and an ack for each one.
    assert list(order) == list(RESET_GOALS)
    assert set(buttons) == set(RESET_GOALS)
    assert set(acks) == set(RESET_GOALS)
    for code in RESET_GOALS:
        assert buttons[code].strip()
        assert acks[code].strip()


def test_reset_block_keeps_handler_contract_fields():
    """Same callback_prefix + header/body shape as the legacy block so the
    handler and analytics stay unchanged; only copy + codes differ."""
    copy = _load_copy()
    legacy = copy["step_1_goal"]
    reset = copy["step_1_goal_reset"]

    assert reset["callback_prefix"] == legacy["callback_prefix"]
    assert reset["header"].strip()
    assert reset["body"].strip()


def test_legacy_goal_block_unchanged():
    """The legacy asset-management block still advertises exactly its three
    codes — the reset copy is additive, never a rewrite of the old flow."""
    from backend.models.onboarding_session import LEGACY_GOALS

    step = _load_copy()["step_1_goal"]
    assert set(step["goal_acks"]) == set(LEGACY_GOALS)
    assert set(step["buttons"]) == set(LEGACY_GOALS)


def test_reset_copy_has_no_forbidden_positioning_terms():
    reset = str(_load_copy()["step_1_goal_reset"]).lower()
    for banned in _FORBIDDEN_TERMS:
        assert banned not in reset, f"forbidden term leaked into reset copy: {banned!r}"


# ----- next_action: CTA matrix resolves the reset codes --------------------


def test_next_action_matrix_covers_reset_goals_in_every_state():
    from backend.models.onboarding_session import RESET_GOALS
    from backend.services.onboarding import next_action_service

    matrix = next_action_service.load_copy()["matrix"]
    buttons = next_action_service.load_copy()["buttons"]
    for state in (
        next_action_service.ASSET_STATE_DEMO,
        next_action_service.ASSET_STATE_REAL_NO_INCOME,
        next_action_service.ASSET_STATE_REAL_WITH_INCOME,
    ):
        row = matrix[state]
        for goal in RESET_GOALS:
            cell = row.get(goal)
            assert cell is not None, f"missing {goal} in {state}"
            assert cell["text"].strip()
            # Every referenced button must exist in the shared button table.
            assert cell["button"] in buttons, cell["button"]


def test_next_action_matrix_falls_back_for_unknown_goal():
    """A goal code with no explicit row still resolves via the
    ``understand_wealth`` fallback baked into ``compute`` — the matrix must keep
    that anchor cell in every state."""
    from backend.models.onboarding_session import GOAL_UNDERSTAND_WEALTH
    from backend.services.onboarding import next_action_service

    matrix = next_action_service.load_copy()["matrix"]
    for state, row in matrix.items():
        anchor = row.get(GOAL_UNDERSTAND_WEALTH)
        assert anchor is not None, f"{state} lost its understand_wealth anchor"
        assert anchor["text"].strip()


# ----- handler: flag drives copy selection ---------------------------------


def test_goal_step_copy_picks_legacy_when_flag_off(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.delenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, raising=False)
    copy = _load_copy()
    assert onboarding_v2._goal_step_copy(copy) is copy["step_1_goal"]


def test_goal_step_copy_picks_reset_when_flag_on(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.setenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, "true")
    copy = _load_copy()
    assert onboarding_v2._goal_step_copy(copy) is copy["step_1_goal_reset"]


def test_goal_step_copy_falls_back_if_reset_block_missing(monkeypatch):
    """Even with the flag on, a copy dict lacking ``step_1_goal_reset`` must not
    strand the user — the helper falls back to the legacy block."""
    from backend.bot.handlers import onboarding_v2

    monkeypatch.setenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, "on")
    copy = {"step_1_goal": {"marker": "legacy"}}
    assert onboarding_v2._goal_step_copy(copy) == {"marker": "legacy"}


def test_flag_helper_reads_env_truthy_and_falsy(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    for on in ("1", "true", "yes", "on", "TRUE", "On"):
        monkeypatch.setenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, on)
        assert onboarding_v2.is_onboarding_reset_enabled() is True, on
    for off in ("0", "false", "no", "off", ""):
        monkeypatch.setenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, off)
        assert onboarding_v2.is_onboarding_reset_enabled() is False, off
    monkeypatch.delenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, raising=False)
    assert onboarding_v2.is_onboarding_reset_enabled() is False


@pytest.mark.asyncio
async def test_send_goal_question_builds_reset_keyboard_from_order(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.models.onboarding_session import RESET_GOALS

    monkeypatch.setenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, "true")

    sent: list[dict] = []

    async def _send(chat_id, text, **kwargs):
        sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return {"result": {"message_id": 1}}

    monkeypatch.setattr(onboarding_v2, "send_message", _send)
    monkeypatch.setattr(onboarding_v2.analytics, "track", lambda *a, **k: None)

    await onboarding_v2._send_goal_question(object(), chat_id=42, user=_user())

    assert len(sent) == 1
    rows = sent[0]["reply_markup"]["inline_keyboard"]
    # One button per reset goal, in the content order.
    codes = [row[0]["callback_data"] for row in rows]
    assert codes == [f"onboarding_v2:goal:{c}" for c in RESET_GOALS]


@pytest.mark.asyncio
async def test_send_goal_question_builds_legacy_keyboard_when_flag_off(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.models.onboarding_session import LEGACY_GOALS

    monkeypatch.delenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, raising=False)

    sent: list[dict] = []

    async def _send(chat_id, text, **kwargs):
        sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return {"result": {"message_id": 1}}

    monkeypatch.setattr(onboarding_v2, "send_message", _send)
    monkeypatch.setattr(onboarding_v2.analytics, "track", lambda *a, **k: None)

    await onboarding_v2._send_goal_question(object(), chat_id=42, user=_user())

    rows = sent[0]["reply_markup"]["inline_keyboard"]
    codes = [row[0]["callback_data"] for row in rows]
    assert codes == [f"onboarding_v2:goal:{c}" for c in LEGACY_GOALS]


@pytest.mark.asyncio
async def test_on_goal_picked_renders_reset_ack_and_accepts_new_code(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.models.onboarding_session import GOAL_EMERGENCY_FUND
    from backend.services.onboarding import onboarding_service

    monkeypatch.setenv(onboarding_v2.ONBOARDING_RESET_FLAG_ENV, "true")

    seen_goal: list[str] = []

    async def _set_goal(_db, _uid, goal, *, trust_card_enabled=True):
        seen_goal.append(goal)
        return SimpleNamespace(current_step="first_asset")

    async def _answer(_cb, **_k):
        return None

    edits: list[str] = []

    async def _edit(**kwargs):
        edits.append(kwargs["text"])

    async def _asset_prompt(_db, _chat_id, _user):
        return None

    monkeypatch.setattr(onboarding_service, "set_goal", _set_goal)
    monkeypatch.setattr(onboarding_v2, "answer_callback", _answer)
    monkeypatch.setattr(onboarding_v2, "edit_message_text", _edit)
    monkeypatch.setattr(onboarding_v2, "_send_first_asset_prompt", _asset_prompt)
    monkeypatch.setattr(onboarding_v2.analytics, "track", lambda *a, **k: None)

    await onboarding_v2._on_goal_picked(
        object(),
        chat_id=55,
        callback_id="cb",
        message_id=9,
        user=_user(),
        goal_code=GOAL_EMERGENCY_FUND,
    )

    # The new code was forwarded to set_goal, and the reset ack (not a legacy
    # one) was edited into the message.
    assert seen_goal == [GOAL_EMERGENCY_FUND]
    expected_ack = _load_copy()["step_1_goal_reset"]["goal_acks"][GOAL_EMERGENCY_FUND]
    assert edits == [expected_ack]
