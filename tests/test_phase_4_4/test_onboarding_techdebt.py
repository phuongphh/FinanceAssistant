"""Tech-debt clean-up tests (Phase 4.4 follow-up).

Two pre-existing violations surfaced by the gates are fixed here:

  1. Layer contract — ``onboarding_service.set_goal`` no longer reads the
     ``TRUST_CARD_ENABLED`` env var. The feature flag is resolved at the
     handler edge and passed in as ``trust_card_enabled``.
  2. i18n — six user-facing strings moved out of
     ``backend/bot/handlers/onboarding_v2.py`` into
     ``content/onboarding/welcome_v2.yaml``.

These tests are DB-free: ``set_goal`` is exercised with a fake session +
fake db so we only assert the routing logic.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from backend.models.onboarding_session import (
    ALL_GOALS,
    STEP_FIRST_ASSET,
    STEP_TRUST_PRIVACY,
)
from backend.services.onboarding import onboarding_service


_VALID_GOAL = next(iter(ALL_GOALS))


class _FakeDB:
    async def flush(self):
        return None


def _patch_session(monkeypatch, session):
    async def _get_session(_db, _uid):
        return session

    monkeypatch.setattr(onboarding_service, "get_session", _get_session)


# ----- B: set_goal is env-free, routes via trust_card_enabled ----------


@pytest.mark.asyncio
async def test_set_goal_routes_to_trust_when_enabled_and_not_accepted(monkeypatch):
    session = SimpleNamespace(
        goal_choice=None, trust_accepted_at=None, current_step="goal_question"
    )
    _patch_session(monkeypatch, session)

    result = await onboarding_service.set_goal(
        _FakeDB(), "uid", _VALID_GOAL, trust_card_enabled=True
    )

    assert result is session
    assert session.goal_choice == _VALID_GOAL
    assert session.current_step == STEP_TRUST_PRIVACY


@pytest.mark.asyncio
async def test_set_goal_skips_trust_when_disabled(monkeypatch):
    session = SimpleNamespace(
        goal_choice=None, trust_accepted_at=None, current_step="goal_question"
    )
    _patch_session(monkeypatch, session)

    await onboarding_service.set_goal(
        _FakeDB(), "uid", _VALID_GOAL, trust_card_enabled=False
    )

    assert session.current_step == STEP_FIRST_ASSET


@pytest.mark.asyncio
async def test_set_goal_skips_trust_when_already_accepted(monkeypatch):
    session = SimpleNamespace(
        goal_choice=None, trust_accepted_at="2026-05-01", current_step="goal_question"
    )
    _patch_session(monkeypatch, session)

    await onboarding_service.set_goal(
        _FakeDB(), "uid", _VALID_GOAL, trust_card_enabled=True
    )

    assert session.current_step == STEP_FIRST_ASSET


@pytest.mark.asyncio
async def test_set_goal_invalid_goal_returns_none(monkeypatch):
    _patch_session(monkeypatch, SimpleNamespace())

    result = await onboarding_service.set_goal(
        _FakeDB(), "uid", "not_a_real_goal", trust_card_enabled=True
    )

    assert result is None


def test_set_goal_does_not_read_env():
    # The env-read helper must no longer live on the service (layer contract).
    assert not hasattr(onboarding_service, "is_trust_card_enabled")
    assert not hasattr(onboarding_service, "TRUST_CARD_FLAG_ENV")


def test_trust_card_flag_lives_at_handler_edge(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.delenv("TRUST_CARD_ENABLED", raising=False)
    assert onboarding_v2.is_trust_card_enabled() is True

    monkeypatch.setenv("TRUST_CARD_ENABLED", "off")
    assert onboarding_v2.is_trust_card_enabled() is False

    monkeypatch.setenv("TRUST_CARD_ENABLED", "true")
    assert onboarding_v2.is_trust_card_enabled() is True


# ----- A: the six moved strings live in the YAML and format cleanly -----


def test_copy_has_new_i18n_keys():
    copy = onboarding_service.load_copy()

    assert copy["step_name"]["prompt"].strip()
    assert copy["step_name"]["invalid"].strip()
    assert copy["next_action"]["session_expired"].strip()
    assert copy["next_action"]["log_expense_prompt"].strip()
    assert copy["next_action"]["default_prompt"].strip()
    assert copy["step_2_asset"]["text_quality_warning"].strip()


def test_text_quality_warning_formats_placeholders():
    copy = onboarding_service.load_copy()
    rendered = copy["step_2_asset"]["text_quality_warning"].format(
        warning="Số hơi lớn so với thường ngày", amount="200tr"
    )
    assert "Số hơi lớn so với thường ngày" in rendered
    assert "200tr" in rendered
    # No leftover placeholders.
    assert "{" not in rendered


def test_moved_strings_not_hardcoded_in_handler():
    handler = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "backend",
        "bot",
        "handlers",
        "onboarding_v2.py",
    )
    with open(handler, encoding="utf-8") as fh:
        src = fh.read()
    for needle in (
        "Trước tiên, Bé Tiền muốn gọi bạn là gì",
        "Tên chưa hợp lệ nè",
        "Gõ /start để bắt đầu nhé",
        "Gõ khoản chi đầu tiên",
        "Gõ /menu để chọn bước tiếp theo",
    ):
        assert needle not in src, f"string still hardcoded: {needle!r}"
