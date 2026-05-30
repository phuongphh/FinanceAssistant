"""Phase 4.4 — The Reading removed; clean goal → asset → Twin flow.

Background
----------
"The Reading" (WOW #1, both v0 the cold-read teaser and v1 the
pre-Twin guess) was cut from the first-5-minutes flow. It hurt more
than it helped:

* **Pain #1 — flow entanglement.** Reading v1 ran only on a *real*
  number (``if not demo and ...``), so tapping the demo button at the
  asset step silently skipped a beat the v0 disclaimer had already
  promised ("cho em xem con số thật"). The demo path broke the wow.
* **Pain #2 — jagged transition.** ack → v1 placeholder → guess →
  v1 disclaimer → "(3/3) Twin" was a self-contradictory triple-promise
  before the payoff.
* **Pain #3 — generic Reading.** v0 fired on zero financial data, so by
  construction it produced Barnum/cold-read flattery — credibility
  poison for a finance product.

Decision (Option A): remove The Reading entirely; keep WOW #0
(salutation) + WOW #3 (proactive empathy); the asset ack now bridges
straight into the Twin reveal as one continuous beat.

This suite locks that contract so the Reading cannot creep back in.
"""

from __future__ import annotations

import importlib
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest


# ----- module no longer carries the Reading wiring ----------------------


def test_reading_flag_helper_removed():
    """``is_reading_enabled`` is gone — no flag, no hook, no env read."""
    from backend.bot.handlers import onboarding_v2

    assert not hasattr(onboarding_v2, "is_reading_enabled")
    assert not hasattr(onboarding_v2, "READING_FLAG_ENV")
    assert not hasattr(onboarding_v2, "_send_reading")


def test_reading_service_module_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("backend.services.reading_service")


def test_reading_prompt_module_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("backend.bot.personality.reading_prompt")


# ----- onboarding copy: no Reading, has the bridging ack ----------------


def test_welcome_copy_has_no_reading_block():
    from backend.services.onboarding import onboarding_service

    copy = onboarding_service.load_copy()
    assert "reading" not in copy


def test_asset_ack_threads_amount_and_name():
    from backend.services.onboarding import onboarding_service

    step = onboarding_service.load_copy()["step_2_asset"]
    ack = step["asset_ack"]
    assert "{amount}" in ack
    assert "{name}" in ack
    formatted = ack.format(amount="200tr", name="anh Minh")
    assert "200tr" in formatted
    assert "anh Minh" in formatted


def test_onboarding_copy_has_no_fortune_telling_register():
    """The cold-read / "bói" voice has no place in a finance product."""
    from backend.services.onboarding import onboarding_service

    raw = str(onboarding_service.load_copy()).lower()
    for banned in ("đoán", "🔮", "bói", "tiên tri"):
        assert banned not in raw, f"fortune-telling token leaked: {banned!r}"


# ----- _save_onboarding_first_asset: one continuous beat ----------------


def _user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        display_name="Minh",
        wizard_state={"flow": "onboarding"},
    )


def _stub_save_deps(monkeypatch):
    """Stub everything ``_save_onboarding_first_asset`` touches except the
    copy lookup, so we can assert on the messages actually sent and on
    the single hand-off into the Twin.
    """
    from backend.bot.handlers import onboarding_v2
    from backend.services.onboarding import onboarding_service
    from backend.twin.services import twin_narrative_service_v2
    from backend.wealth.services import asset_service

    sent: list[str] = []
    twin_calls: list[dict] = []

    async def _send(chat_id, text, **_k):
        sent.append(text)
        return {"result": {"message_id": 7}}

    async def _create_asset(*_a, **_k):
        return SimpleNamespace(id=uuid.uuid4())

    async def _set_first_asset(_db, _uid, _value, *, demo):
        return None

    async def _flush():
        return None

    async def _trigger(db, chat_id, user, *, demo):
        twin_calls.append({"demo": demo})

    monkeypatch.setattr(onboarding_v2, "send_message", _send)
    monkeypatch.setattr(asset_service, "create_asset", _create_asset)
    monkeypatch.setattr(onboarding_service, "set_first_asset", _set_first_asset)
    monkeypatch.setattr(onboarding_v2, "_trigger_first_twin", _trigger)
    monkeypatch.setattr(twin_narrative_service_v2, "demo_ack_text", lambda: "DEMO_ACK")
    monkeypatch.setattr(onboarding_v2.analytics, "track", lambda *a, **k: None)
    return sent, twin_calls


@pytest.mark.asyncio
async def test_real_number_acks_then_goes_straight_to_twin(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    sent, twin_calls = _stub_save_deps(monkeypatch)

    db = SimpleNamespace(flush=_noop_flush)
    user = _user()
    await onboarding_v2._save_onboarding_first_asset(
        db,
        chat_id=123,
        user=user,
        value=Decimal("200000000"),
        raw_text="200tr",
        warning_type=None,
        demo=False,
    )

    # Exactly one ack message before the Twin — no Reading detour.
    assert len(sent) == 1
    ack = sent[0]
    assert "Minh" in ack  # {name} threaded from display_name
    assert "200" in ack  # {amount} threaded (formatted figure)
    assert "đoán" not in ack.lower() and "🔮" not in ack
    # The ack bridges directly into the single Twin hand-off.
    assert twin_calls == [{"demo": False}]


@pytest.mark.asyncio
async def test_real_number_name_falls_back_to_ban(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    sent, _ = _stub_save_deps(monkeypatch)

    db = SimpleNamespace(flush=_noop_flush)
    user = SimpleNamespace(id=uuid.uuid4(), display_name=None, wizard_state=None)
    await onboarding_v2._save_onboarding_first_asset(
        db,
        chat_id=123,
        user=user,
        value=Decimal("200000000"),
        raw_text="200tr",
        warning_type=None,
        demo=False,
    )
    assert "bạn" in sent[0]


@pytest.mark.asyncio
async def test_demo_uses_demo_ack_then_twin(monkeypatch):
    """Demo path stays clean too: its own ack, then the Twin — the demo
    button no longer skips a Reading beat (the original Pain #1)."""
    from backend.bot.handlers import onboarding_v2

    sent, twin_calls = _stub_save_deps(monkeypatch)

    db = SimpleNamespace(flush=_noop_flush)
    user = _user()
    await onboarding_v2._save_onboarding_first_asset(
        db,
        chat_id=123,
        user=user,
        value=Decimal("50000000"),
        raw_text="demo",
        warning_type=None,
        demo=True,
    )
    assert sent == ["DEMO_ACK"]
    assert twin_calls == [{"demo": True}]


# ----- _on_goal_picked: straight to the asset prompt, no Reading --------


@pytest.mark.asyncio
async def test_goal_pick_routes_to_asset_prompt_no_reading(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.services.onboarding import onboarding_service

    async def _set_goal(_db, _uid, _goal, *, trust_card_enabled=True):
        # Not on the trust step → flow goes to the asset prompt.
        return SimpleNamespace(current_step=STEP_FIRST_ASSET_SENTINEL)

    async def _answer(_cb, **_k):
        return None

    async def _edit(**_k):
        return None

    prompts: list[int] = []

    async def _asset_prompt(_db, chat_id, _user):
        prompts.append(chat_id)

    monkeypatch.setattr(onboarding_service, "set_goal", _set_goal)
    monkeypatch.setattr(onboarding_v2, "answer_callback", _answer)
    monkeypatch.setattr(onboarding_v2, "edit_message_text", _edit)
    monkeypatch.setattr(onboarding_v2, "_send_first_asset_prompt", _asset_prompt)
    monkeypatch.setattr(onboarding_v2.analytics, "track", lambda *a, **k: None)

    user = _user()
    await onboarding_v2._on_goal_picked(
        object(),
        chat_id=55,
        callback_id="cb",
        message_id=9,
        user=user,
        goal_code="understand_wealth",
    )
    # Lands on the asset prompt with no intervening Reading send.
    assert prompts == [55]


# A current_step value that is NOT STEP_TRUST_PRIVACY so _on_goal_picked
# takes the asset-prompt branch.
STEP_FIRST_ASSET_SENTINEL = "first_asset"


async def _noop_flush():
    return None
