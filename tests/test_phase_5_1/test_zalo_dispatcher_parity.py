"""Phase 5.1 #4.1 — Zalo runs on the *same* dispatcher as Telegram.

``tests/test_phase_5_0/test_zalo_inbound_handler.py`` tests the handler's
branches with a fake dispatcher: which path fires, and what it says. This
file tests the seam the other side of that fake — the real
:class:`~backend.intent.dispatcher.IntentDispatcher`, driven through
``handle_inbound_event`` exactly as the worker drives it.

Two things are being asserted, and they are different claims:

1. **Parity** — a main intent classified on Zalo comes back out as a Zalo
   bubble. This is the DoD's ≥6-intent integration test. The whitelist it
   replaces meant "Zalo answers seven things"; the point of #4.1 is that
   the number is now "whatever Telegram answers", so the list below is a
   sample of that, not a new whitelist. Nothing in the production path is
   stubbed except the transport and the handler *bodies* — CI has no
   database, so a handler that reads one cannot run here. Everything
   between the classifier and the bubble is real: the confidence policy,
   the personality wrap, the follow-up picker, the markdown flattening.

2. **Agreement** — :func:`persists_flow_state` says what ``dispatch``
   does. That predicate is a hand-written mirror of two branch conditions
   in another module, and its own docstring promises "the parity suite
   asserts they agree", which is this. The failure it guards against is
   silent and one-directional: if the dispatcher grows a third branch
   that persists state and the predicate misses it, nothing breaks on
   Telegram and Zalo starts arming flow state that only Telegram can
   disarm. So the check drives the real ``dispatch`` over a grid of
   *every* intent × the whole confidence ladder and compares what was
   actually written against what the predicate promised.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from backend.bot.handlers import zalo_inbound
from backend.intent import pending_action
from backend.intent.dispatcher import (
    CONFIRM_THRESHOLD,
    EXECUTE_THRESHOLD,
    WIZARD_LAUNCHING_INTENTS,
    IntentDispatcher,
    persists_flow_state,
)
from backend.intent.intents import CLASSIFIER_RULE, IntentResult, IntentType
from backend.utils.zalo_copy import text as zalo_copy_text
from backend.utils.zalo_events import ZaloEvent

SENDER_ID = "zalo-sender-parity"


# ---------------------------------------------------------------------------
# Fixtures — transport out, intent stack in
# ---------------------------------------------------------------------------


class _SpyNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))
        return {"ok": True}


class _SpySession:
    """A session that answers the one read the handler makes.

    ``is_user_allowed`` reads ``users.manual_status``; everything else
    raises, so a handler body that quietly reached for the database would
    fail here rather than pass against a permissive mock.
    """

    async def scalar(self, _stmt):
        return "active"

    async def commit(self):  # pragma: no cover - asserted, not exercised
        raise AssertionError("handler must not commit — the worker does")

    async def flush(self):  # pragma: no cover
        raise AssertionError("handler must not flush")

    async def execute(self, _stmt):  # pragma: no cover
        raise AssertionError("no test here should reach the database")


class _FakeUser:
    """Enough of ``User`` for the personality wrap and the follow-up picker.

    ``wealth_level`` is left unset on purpose: ``_execute`` reads it with
    ``getattr(user, ..., None)`` and the picker falls back to the base
    pool, which is the shape a brand-new Zalo signup actually has.
    """

    def __init__(self) -> None:
        self.id = uuid4()
        self.telegram_id = None
        self.display_name = "An"


class _StubHandler:
    """A handler body, minus the database.

    Returns a fixed string so the assertion can be "this text reached the
    bubble" rather than "something did". Counting calls is what makes the
    negative cases meaningful — an intent held back must leave this at 0.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def handle(self, intent, user, db) -> str:
        self.calls += 1
        return self.text


def _event(text: str) -> ZaloEvent:
    return ZaloEvent(
        msg_id="m-parity",
        event_name="user_send_text",
        sender_id=SENDER_ID,
        text=text,
        timestamp="1754092800000",
        derived_key=None,
        payload={},
    )


def _result(intent: IntentType, confidence: float) -> IntentResult:
    return IntentResult(
        intent=intent,
        confidence=confidence,
        raw_text="",
        classifier_used=CLASSIFIER_RULE,
    )


@pytest.fixture()
def zalo_out(monkeypatch):
    """Both transports replaced — nothing in this module reaches a network."""
    zalo = _SpyNotifier()
    monkeypatch.setattr(
        zalo_inbound, "build_zalo_notifier", lambda zalo_user_id, **kwargs: zalo
    )
    monkeypatch.setattr(zalo_inbound, "get_notifier", lambda: _SpyNotifier())
    return zalo


@pytest.fixture()
def linked_user(monkeypatch):
    """Make the sender a linked user, so messages reach the intent path."""
    user = _FakeUser()

    async def _get_linked_user(db, zalo_user_id):
        return user

    monkeypatch.setattr(
        zalo_inbound.zalo_linking_service, "get_linked_user", _get_linked_user
    )
    return user


@pytest.fixture(autouse=True)
def _onboarding_declines(monkeypatch):
    """Onboarding gets first refusal on every inbound text (#4.3).

    This module is about what happens *after* it declines, so it always
    declines here. The step machine itself is exercised for real in
    ``test_zalo_onboarding.py``.
    """

    async def _handle_text(db, *, notifier, user, text):
        return False

    monkeypatch.setattr(zalo_inbound.zalo_onboarding, "handle_text", _handle_text)


@pytest.fixture(autouse=True)
def _no_catchup(monkeypatch):
    """Catch-up stays out of this module's way (#4.5).

    ``handle_inbound_event`` now asks ``zalo_catchup_service`` whether a
    returning Zalo-only user missed anything, which is a database read.
    The handler swallows failures on purpose — an answer must not be lost
    because the catch-up line could not be built — so without this stub
    ``_SpySession.execute``'s deliberate "no test here should reach the
    database" would be caught and discarded, and the guard would stop
    guarding. Catch-up is proved for real in ``test_zalo_catchup.py``.
    """

    async def _none(db, **kwargs):
        return None

    monkeypatch.setattr(zalo_inbound.zalo_catchup_service, "build_catchup_line", _none)


@pytest.fixture()
def real_dispatcher():
    """A genuine :class:`IntentDispatcher`, freshly built per test."""
    return IntentDispatcher()


def _seed(dispatcher: IntentDispatcher, intent: IntentType, text: str) -> _StubHandler:
    """Give ``intent`` a body that answers with ``text`` and touches no DB.

    Handlers are written straight into the private registry rather than
    monkeypatched onto ``_build_handler``: ``_get_handler`` reads the
    cache first, so a seeded entry short-circuits the lazy import of a
    module that would want a database. Meta intents (greeting, help) are
    deliberately *not* seeded anywhere in this file — those handlers are
    pure string builders, so the real ones run.
    """
    handler = _StubHandler(text)
    dispatcher._handlers[intent] = handler
    return handler


def _install(monkeypatch, dispatcher, result: IntentResult):
    """Point the lazily-imported intent stack at our classifier + dispatcher."""
    from backend.bot.handlers import free_form_text

    class _Pipeline:
        async def classify(self, _text: str) -> IntentResult:
            return result

    monkeypatch.setattr(free_form_text, "get_pipeline", lambda: _Pipeline())
    monkeypatch.setattr(free_form_text, "get_dispatcher", lambda: dispatcher)


# ---------------------------------------------------------------------------
# 1. Parity — main intents come back as Zalo bubbles
# ---------------------------------------------------------------------------

# Intent → (the message a user would send, the answer its handler returns).
# The answers carry a distinctive token so an assertion cannot pass on a
# fallback bubble that happens to be non-empty. Markdown is included on
# purpose: flattening it is part of what "came out as a Zalo bubble" means.
SERVED_INTENTS = {
    IntentType.QUERY_NET_WORTH: (
        "tài sản ròng của tôi",
        "*Tài sản ròng:* 1,2 tỷ",
    ),
    IntentType.QUERY_ASSETS: (
        "tài sản của tôi có gì",
        "Bạn đang có *3 tài sản*",
    ),
    IntentType.QUERY_EXPENSES: (
        "chi tiêu tháng này",
        "Tháng này bạn tiêu *12,5tr*",
    ),
    IntentType.QUERY_EXPENSES_BY_CATEGORY: (
        "chi tiêu ăn uống tháng này",
        "Ăn uống: 4,2tr",
    ),
    IntentType.QUERY_GOALS: (
        "mục tiêu của tôi",
        "Mục tiêu mua nhà: 45%",
    ),
    IntentType.QUERY_TWIN: (
        "twin của tôi",
        "Bản sao tài chính: đang đi đúng hướng",
    ),
    IntentType.QUERY_MARKET: (
        "VNM giá bao nhiêu",
        "VNM: 62.400đ",
    ),
    IntentType.QUERY_CASHFLOW: (
        "dòng tiền tháng này",
        "Vào 30tr · Ra 18tr",
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "message", "answer"),
    [(intent, msg, ans) for intent, (msg, ans) in SERVED_INTENTS.items()],
    ids=[intent.value for intent in SERVED_INTENTS],
)
async def test_a_main_intent_is_answered_on_zalo(
    monkeypatch, zalo_out, linked_user, real_dispatcher, intent, message, answer
):
    """Eight intents, none of which Zalo could answer before #4.1.

    The assertion is deliberately ``in`` rather than ``==``: ``_execute``
    wraps read answers with the personality layer, which prepends a
    greeting and appends a suggestion at random. Pinning the whole string
    would make this a test of ``random.seed``.
    """
    handler = _seed(real_dispatcher, intent, answer)
    _install(monkeypatch, real_dispatcher, _result(intent, 0.95))

    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(message))

    assert handler.calls == 1
    assert len(zalo_out.sent) == 1
    chat_id, body = zalo_out.sent[0]
    # Zalo's notifier addresses the recipient itself; the 0 is a
    # placeholder the port requires, not a chat id.
    assert chat_id == 0
    # The answer survived — stripped of markup, which is the renderer's
    # job and is why the seeded text carries asterisks.
    assert answer.replace("*", "") in body
    assert "*" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", [IntentType.GREETING, IntentType.HELP])
async def test_a_meta_intent_runs_its_real_handler(
    monkeypatch, zalo_out, linked_user, real_dispatcher, intent
):
    """Greeting and help take the meta short-circuit, not the confidence
    policy — a different branch of ``dispatch``, so worth its own case.

    Nothing is seeded here: :class:`GreetingHandler` and
    :class:`HelpHandler` are pure string builders, so these two go through
    production code end to end. Help's copy is full of ``*bold*`` section
    headers, which makes it the strongest flattening case in the file.
    """
    _install(monkeypatch, real_dispatcher, _result(intent, 0.99))

    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event("chào bé"))

    assert len(zalo_out.sent) == 1
    body = zalo_out.sent[0][1]
    assert linked_user.display_name in body
    assert "*" not in body


@pytest.mark.asyncio
async def test_a_self_sending_handler_produces_no_second_bubble(
    monkeypatch, zalo_out, linked_user, real_dispatcher
):
    """``action_quick_transaction`` sends its own confirmation card (#2.4
    made that channel-aware). The dispatcher then returns empty text, and
    the handler must read that as "already answered" rather than as a bug
    to paper over with a fallback — otherwise the user sees their
    transaction acknowledged twice.
    """
    handler = _seed(real_dispatcher, IntentType.ACTION_QUICK_TRANSACTION, "")
    _install(
        monkeypatch,
        real_dispatcher,
        _result(IntentType.ACTION_QUICK_TRANSACTION, 0.95),
    )

    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event("ăn trưa 50k"))

    assert handler.calls == 1
    assert zalo_out.sent == []


@pytest.mark.asyncio
async def test_a_wizard_intent_is_declined_before_it_can_send_to_telegram(
    monkeypatch, zalo_out, linked_user, real_dispatcher
):
    """The negative half of parity, end to end against the real dispatcher.

    ``action_add_asset`` pushes a Telegram keyboard from inside its own
    handler. Since #4.2 a Zalo-only user has ``telegram_id = None``, so
    running it would send to ``chat_id=None``. The seeded stub therefore
    stands in for a handler that must never be reached — ``calls == 0``
    is the assertion, and the copy is the consolation prize.
    """
    handler = _seed(real_dispatcher, IntentType.ACTION_ADD_ASSET, "keyboard")
    _install(monkeypatch, real_dispatcher, _result(IntentType.ACTION_ADD_ASSET, 0.95))

    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event("thêm tài sản"))

    assert handler.calls == 0
    assert zalo_out.sent == [(0, zalo_copy_text("fallback", "unsupported"))]


# ---------------------------------------------------------------------------
# 2. Agreement — the predicate matches what dispatch actually writes
# ---------------------------------------------------------------------------


# The whole ladder, including both boundaries. 0.0 is separate from 0.3
# because ``_build_clarification`` treats "no signal at all" as UNCLEAR
# and persists nothing; the two thresholds are included exactly because
# ``<`` versus ``<=`` is the classic place a mirrored condition drifts.
CONFIDENCE_LADDER = (
    0.0,
    0.3,
    CONFIRM_THRESHOLD - 0.01,
    CONFIRM_THRESHOLD,
    0.65,
    EXECUTE_THRESHOLD - 0.01,
    EXECUTE_THRESHOLD,
    0.95,
)


@pytest.mark.asyncio
async def test_persists_flow_state_agrees_with_the_dispatcher(monkeypatch):
    """Every intent × the whole confidence ladder, predicted then observed.

    ``set_pending_action`` and ``set_awaiting_clarification`` are replaced
    with recorders — they are the only two writes the predicate is about,
    and swapping them is also what lets this run without a database.

    Every intent gets a seeded handler so the execute path is uniform:
    an unseeded intent would return ``not_implemented``, which persists
    nothing and would let a mismatch on the execute branch pass unnoticed.
    """
    dispatcher = IntentDispatcher()
    for intent in IntentType:
        dispatcher._handlers[intent] = _StubHandler("ok")

    writes: list[str] = []

    async def _record_pending(db, user, **kwargs):
        writes.append("pending_action")

    async def _record_clarify(db, user, **kwargs):
        writes.append("awaiting_clarification")

    monkeypatch.setattr(pending_action, "set_pending_action", _record_pending)
    monkeypatch.setattr(pending_action, "set_awaiting_clarification", _record_clarify)

    user = _FakeUser()
    db = _SpySession()
    mismatches: list[str] = []

    for intent in IntentType:
        for confidence in CONFIDENCE_LADDER:
            result = _result(intent, confidence)
            predicted = persists_flow_state(result)

            writes.clear()
            await dispatcher.dispatch(result, user, db)
            observed = bool(writes)

            if predicted != observed:
                mismatches.append(
                    f"{intent.value} @ {confidence}: "
                    f"predicted={predicted} observed={observed} ({writes})"
                )

    assert not mismatches, "persists_flow_state drifted from dispatch:\n" + "\n".join(
        mismatches
    )


@pytest.mark.asyncio
async def test_nothing_zalo_serves_writes_flow_state(monkeypatch):
    """The invariant that motivates the predicate, stated as a property.

    The test above proves the predicate is honest about ``dispatch``.
    This one proves the handler *uses* it correctly: run the same grid
    through ``_unserved_reason`` and dispatch only what it clears — no
    write may happen. A regression in either the predicate or the
    handler's use of it shows up here as a non-empty list.
    """
    dispatcher = IntentDispatcher()
    for intent in IntentType:
        dispatcher._handlers[intent] = _StubHandler("ok")

    leaked: list[str] = []

    async def _leak(db, user, **kwargs):
        leaked.append("write")

    monkeypatch.setattr(pending_action, "set_pending_action", _leak)
    monkeypatch.setattr(pending_action, "set_awaiting_clarification", _leak)

    user = _FakeUser()
    db = _SpySession()
    served: list[IntentType] = []

    for intent in IntentType:
        for confidence in CONFIDENCE_LADDER:
            result = _result(intent, confidence)
            if zalo_inbound._unserved_reason(result) is not None:
                continue
            served.append(intent)
            await dispatcher.dispatch(result, user, db)

    assert leaked == []
    # Guard against the degenerate pass: if the blocklist ever widened to
    # everything, the loop above would write nothing for the wrong reason.
    assert len(set(served)) > 6


def test_the_blocklist_covers_every_self_sending_handler():
    """``WIZARD_LAUNCHING_INTENTS`` is the blocklist *and* the dispatcher's
    own "skip the personality wrap" table. This asserts the property that
    makes reusing it sound rather than convenient: every intent in it is
    one whose handler talks to Telegram itself.

    Checked against the source of the handler modules because the
    behaviour — "this one sends its own message" — has no runtime marker
    to assert on, and the alternative is a second hand-written list that
    rots the same way the whitelist did.
    """
    import pathlib

    handlers_dir = (
        pathlib.Path(zalo_inbound.__file__).parents[2] / "intent" / "handlers"
    )
    self_sending = {
        path.stem
        for path in handlers_dir.glob("*.py")
        if "telegram_id" in path.read_text(encoding="utf-8")
    }

    assert self_sending == {intent.value for intent in WIZARD_LAUNCHING_INTENTS}


def test_no_service_branches_on_the_zalo_channel():
    """Phase 5.1's governing rule, as a test rather than a review note:
    there is no "Zalo version" of any service. Channel difference lives in
    the renderer, the notifier, the button mapper and ``content/zalo.yaml``
    — if a service ever needs to know, the design took a wrong turn.
    """
    import pathlib

    services = pathlib.Path(zalo_inbound.__file__).parents[2] / "services"
    offenders = [
        str(path)
        for path in services.rglob("*.py")
        if 'channel == "zalo"' in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
