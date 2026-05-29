"""Phase 4.4 Epic 0 — Salutation Foundation.

Covers the pure salutation helper, the flush-only ``set_salutation``
mutator, the twin-narrative threading, and the onboarding copy so
Bé Tiền can address the user as anh/chị/bạn.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest


# ----- salutation_of (pure) ---------------------------------------------


def test_salutation_of_none_user_falls_back_to_ban():
    from backend.services.onboarding.onboarding_service import salutation_of

    assert salutation_of(None) == "bạn"


@pytest.mark.parametrize("value", ["anh", "chị", "bạn"])
def test_salutation_of_returns_valid_value(value):
    from backend.services.onboarding.onboarding_service import salutation_of

    assert salutation_of(SimpleNamespace(salutation=value)) == value


@pytest.mark.parametrize("value", [None, "", "   ", "sir", "ông", "EM"])
def test_salutation_of_unknown_or_null_falls_back_to_ban(value):
    from backend.services.onboarding.onboarding_service import salutation_of

    assert salutation_of(SimpleNamespace(salutation=value)) == "bạn"


# ----- set_salutation (flush-only mutator) ------------------------------


class _FakeDB:
    """Minimal AsyncSession stub: ``get`` returns a preset user."""

    def __init__(self, user=None):
        self._user = user
        self.flushed = False
        self.committed = False

    async def get(self, _model, _id):
        return self._user

    async def flush(self):
        self.flushed = True

    async def commit(self):  # pragma: no cover - guard, must never be hit
        self.committed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["anh", "chị", "bạn"])
async def test_set_salutation_persists_valid(value):
    from backend.services.onboarding.onboarding_service import set_salutation

    user = SimpleNamespace(id=uuid.uuid4(), salutation=None)
    db = _FakeDB(user)
    out = await set_salutation(db, user.id, value)

    assert out is user
    assert user.salutation == value
    assert db.flushed is True
    # Service layer must NEVER commit (layer contract).
    assert db.committed is False


@pytest.mark.asyncio
async def test_set_salutation_rejects_unknown_value():
    from backend.services.onboarding.onboarding_service import set_salutation

    user = SimpleNamespace(id=uuid.uuid4(), salutation=None)
    db = _FakeDB(user)
    out = await set_salutation(db, user.id, "ông")

    assert out is None
    assert user.salutation is None
    assert db.flushed is False


@pytest.mark.asyncio
async def test_set_salutation_missing_user_returns_none():
    from backend.services.onboarding.onboarding_service import set_salutation

    db = _FakeDB(user=None)
    out = await set_salutation(db, uuid.uuid4(), "anh")

    assert out is None
    assert db.flushed is False


# ----- twin narrative threading -----------------------------------------


def test_narrative_text_threads_salutation():
    from backend.twin.services import twin_narrative_service_v2 as svc

    text = svc.narrative_text(salutation="anh")
    assert "của anh" in text
    # Sentence-start form must be capitalized, not raw "anh".
    assert "Anh không cần đoán tương lai" in text


def test_narrative_text_defaults_to_ban():
    from backend.twin.services import twin_narrative_service_v2 as svc

    text = svc.narrative_text()
    assert "của bạn" in text
    assert "Bạn không cần đoán tương lai" in text


def test_demo_narrative_threads_salutation():
    from backend.twin.services import twin_narrative_service_v2 as svc

    text = svc.narrative_text(demo=True, salutation="chị")
    assert "của chị" in text


# ----- onboarding copy ---------------------------------------------------


def test_welcome_copy_has_salutation_step_with_all_options():
    from backend.services.onboarding import onboarding_service

    step = onboarding_service.load_copy()["step_salutation"]
    for key in ("anh", "chị", "bạn"):
        assert step["buttons"][key], f"missing salutation button {key}"
        assert step["acks"][key], f"missing salutation ack {key}"
    assert step["callback_prefix"] == "onboarding_v2:salutation:"


def test_welcome_copy_has_no_cfo_wording():
    from backend.services.onboarding import onboarding_service

    raw = str(onboarding_service.load_copy()).lower()
    # "CFO" reads cold/corporate — banned from user-facing text.
    assert "cfo" not in raw
