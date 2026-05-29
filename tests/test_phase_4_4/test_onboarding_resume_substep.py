"""Phase 4.4 — onboarding resume sub-step correctness.

Fixes the "two flows at once" onboarding bug: the name + salutation
sub-steps are collapsed into the single ``goal_question`` DB step, so the
resume nudge cron and the resume button must derive the live sub-step from
the ``User`` row instead of assuming the user is stuck at goal pick.

Covers:
  - ``goal_substep`` pure derivation (name → salutation → goal)
  - ``_resume_at`` routes to the correct sub-step (never skips name/salutation)
  - resume-nudge job skips the name/salutation intro sub-steps
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from backend.models.onboarding_session import (
    STEP_FIRST_ASSET,
    STEP_GOAL_QUESTION,
    STEP_TWIN_SHOWN,
)


# ----- goal_substep (pure) ----------------------------------------------


def test_goal_substep_no_user_is_name():
    from backend.services.onboarding.onboarding_service import (
        SUBSTEP_NAME,
        goal_substep,
    )

    assert goal_substep(None) == SUBSTEP_NAME


@pytest.mark.parametrize("display_name", [None, "", "   "])
def test_goal_substep_missing_name_is_name(display_name):
    from backend.services.onboarding.onboarding_service import (
        SUBSTEP_NAME,
        goal_substep,
    )

    user = SimpleNamespace(display_name=display_name, salutation=None)
    assert goal_substep(user) == SUBSTEP_NAME


@pytest.mark.parametrize("salutation", [None, "", "   "])
def test_goal_substep_name_set_no_salutation_is_salutation(salutation):
    from backend.services.onboarding.onboarding_service import (
        SUBSTEP_SALUTATION,
        goal_substep,
    )

    user = SimpleNamespace(display_name="Phương", salutation=salutation)
    assert goal_substep(user) == SUBSTEP_SALUTATION


@pytest.mark.parametrize("salutation", ["anh", "chị", "bạn"])
def test_goal_substep_name_and_salutation_set_is_goal(salutation):
    from backend.services.onboarding.onboarding_service import (
        SUBSTEP_GOAL,
        goal_substep,
    )

    user = SimpleNamespace(display_name="Phương", salutation=salutation)
    assert goal_substep(user) == SUBSTEP_GOAL


# ----- _resume_at routing -----------------------------------------------


class _RecordingResume:
    """Patches the three send helpers and records which one fired."""

    def __init__(self, monkeypatch):
        from backend.bot.handlers import onboarding_v2

        self.calls: list[str] = []

        async def _name(chat_id):
            self.calls.append("name")

        async def _salutation(db, chat_id, user):
            self.calls.append("salutation")

        async def _goal(db, chat_id, user):
            self.calls.append("goal")

        monkeypatch.setattr(onboarding_v2, "_send_name_prompt", _name)
        monkeypatch.setattr(onboarding_v2, "_send_salutation_question", _salutation)
        monkeypatch.setattr(onboarding_v2, "_send_goal_question", _goal)


@pytest.mark.asyncio
async def test_resume_at_goal_step_no_name_resends_name(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    rec = _RecordingResume(monkeypatch)
    user = SimpleNamespace(id=uuid.uuid4(), display_name=None, salutation=None)
    session = SimpleNamespace(current_step=STEP_GOAL_QUESTION)

    await onboarding_v2._resume_at(db=None, chat_id=1, user=user, session=session)

    assert rec.calls == ["name"]


@pytest.mark.asyncio
async def test_resume_at_goal_step_name_only_resends_salutation(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    rec = _RecordingResume(monkeypatch)
    user = SimpleNamespace(id=uuid.uuid4(), display_name="Phương", salutation=None)
    session = SimpleNamespace(current_step=STEP_GOAL_QUESTION)

    await onboarding_v2._resume_at(db=None, chat_id=1, user=user, session=session)

    assert rec.calls == ["salutation"]


@pytest.mark.asyncio
async def test_resume_at_goal_step_name_and_salutation_resends_goal(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    rec = _RecordingResume(monkeypatch)
    user = SimpleNamespace(id=uuid.uuid4(), display_name="Phương", salutation="chị")
    session = SimpleNamespace(current_step=STEP_GOAL_QUESTION)

    await onboarding_v2._resume_at(db=None, chat_id=1, user=user, session=session)

    # Both sub-steps done → goal question, never skipping back over them.
    assert rec.calls == ["goal"]


# ----- resume-nudge job skip predicate ----------------------------------


def test_intro_substep_true_for_name_stage():
    from backend.jobs.onboarding_resume_job import _is_intro_substep

    user = SimpleNamespace(display_name=None, salutation=None)
    session = SimpleNamespace(current_step=STEP_GOAL_QUESTION)
    assert _is_intro_substep(session, user) is True


def test_intro_substep_true_for_salutation_stage():
    from backend.jobs.onboarding_resume_job import _is_intro_substep

    user = SimpleNamespace(display_name="Phương", salutation=None)
    session = SimpleNamespace(current_step=STEP_GOAL_QUESTION)
    assert _is_intro_substep(session, user) is True


def test_intro_substep_false_at_goal_pick():
    from backend.jobs.onboarding_resume_job import _is_intro_substep

    user = SimpleNamespace(display_name="Phương", salutation="anh")
    session = SimpleNamespace(current_step=STEP_GOAL_QUESTION)
    # Name + salutation done → genuinely stuck at goal pick → nudge is OK.
    assert _is_intro_substep(session, user) is False


@pytest.mark.parametrize("step", [STEP_FIRST_ASSET, STEP_TWIN_SHOWN])
def test_intro_substep_false_for_later_steps(step):
    from backend.jobs.onboarding_resume_job import _is_intro_substep

    # Even with a NULL name (unlikely past goal_question), later steps are
    # never treated as the intro sub-step — the nudge stays eligible there.
    user = SimpleNamespace(display_name=None, salutation=None)
    session = SimpleNamespace(current_step=step)
    assert _is_intro_substep(session, user) is False


# ----- touch_session (resume-nudge delay measured from latest activity) ---


class _FakeDB:
    """Minimal async DB stub: resolves ``get`` from a preloaded map."""

    def __init__(self, session):
        self._session = session
        self.flushed = False

    async def get(self, model, pk):
        return self._session

    async def flush(self):
        self.flushed = True


@pytest.mark.asyncio
async def test_touch_session_bumps_updated_at():
    import datetime as _dt

    from backend.services.onboarding import onboarding_service

    stale = _dt.datetime(2020, 1, 1, tzinfo=_dt.timezone.utc)
    session = SimpleNamespace(current_step=STEP_GOAL_QUESTION, updated_at=stale)
    db = _FakeDB(session)

    before = _dt.datetime.now(_dt.timezone.utc)
    result = await onboarding_service.touch_session(db, uuid.uuid4())
    after = _dt.datetime.now(_dt.timezone.utc)

    assert result is session
    # updated_at moved off the stale /start timestamp to "now".
    assert session.updated_at > stale
    assert before <= session.updated_at <= after
    # Flush-only: the mutator must persist via flush, never commit.
    assert db.flushed is True


@pytest.mark.asyncio
async def test_touch_session_missing_returns_none():
    from backend.services.onboarding import onboarding_service

    db = _FakeDB(None)
    result = await onboarding_service.touch_session(db, uuid.uuid4())

    assert result is None
    # No row to bump → no flush.
    assert db.flushed is False
