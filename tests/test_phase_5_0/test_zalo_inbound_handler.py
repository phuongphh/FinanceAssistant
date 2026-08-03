"""Phase 5.0 #2.2 + #2.3 — the inbound handler's routing decisions.

One branch per message, and each branch has a user-visible consequence:

* a pasted ``BT-XXXXXX`` code links the account and confirms on *both*
  channels (the code was issued in Telegram — the loop closes where the
  user started it);
* a linked sender gets their message classified and answered — dispatched
  for real, or answered with the fallback that names *why* not;
* an unlinked sender is signed up on the spot rather than told to go
  find a code somewhere else.

Also pins the things that must never happen: no ``db.commit()`` from the
handler (the worker owns the boundary), no token, sender id or message
text in the logs, and no dispatch of an intent that would leave Telegram
flow state armed behind it.

Phase 5.1 #4.1 replaced the seven-intent whitelist these tests were
written against with a two-class blocklist, and #4.3 replaced the
"/link_zalo" nudge with a signup. The routing assertions moved with them;
everything else (linking, suspension, markup flattening, telemetry
hygiene) is unchanged and still lives here.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from backend.bot.handlers import zalo_inbound
from backend.intent.dispatcher import (
    CONFIRM_THRESHOLD,
    OUTCOME_EXECUTED,
    WIZARD_LAUNCHING_INTENTS,
    WRITE_INTENTS,
    DispatchOutcome,
)
from backend.intent.intents import CLASSIFIER_RULE, IntentResult, IntentType
from backend.services.user_status import STATUS_ACTIVE, STATUS_SUSPENDED
from backend.services.zalo_linking_service import LinkRedemption
from backend.utils import zalo_copy
from backend.utils.zalo_events import ZaloEvent

SENDER_ID = "zalo-sender-should-never-be-logged"
TOKEN = "BT-ABC234"


def _result(intent: IntentType, confidence: float) -> IntentResult:
    """A classification result, for the checks that call the routing
    predicate directly instead of driving a whole message through."""
    return IntentResult(
        intent=intent,
        confidence=confidence,
        raw_text="",
        classifier_used=CLASSIFIER_RULE,
    )


def _event(
    text: str = "ăn trưa 50k", *, event_name: str = "user_send_text"
) -> ZaloEvent:
    return ZaloEvent(
        msg_id="m-1",
        event_name=event_name,
        sender_id=SENDER_ID,
        text=text,
        timestamp="1754092800000",
        derived_key=None,
        payload={},
    )


class _SpySession:
    """Fails loudly if the handler tries to own a transaction.

    Also serves the one read the handler makes through a service that
    still needs the session: ``is_user_allowed`` looks up
    ``users.manual_status`` (#5). Modelling it as a plain scalar keeps
    this module free of the ORM — the value is all the gate looks at.
    """

    def __init__(self, *, manual_status: str = STATUS_ACTIVE) -> None:
        self.committed = False
        self.manual_status = manual_status
        self.scalars_read = 0

    async def scalar(self, _stmt):
        self.scalars_read += 1
        return self.manual_status

    async def commit(self):  # pragma: no cover — asserted, not exercised
        self.committed = True
        raise AssertionError("handler must not commit — the worker does")

    async def flush(self):  # pragma: no cover
        raise AssertionError("handler must not flush")


class _FakeUser:
    def __init__(self, telegram_id: int | None = 555):
        self.id = uuid4()
        self.telegram_id = telegram_id


class _SpyNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))
        return {"ok": True}


@pytest.fixture(autouse=True)
def _isolate_channel(monkeypatch):
    """Replace both transports so no test can reach the network.

    The handler builds its Zalo notifier through
    :func:`build_zalo_notifier` (#3.2), so that factory is the seam we
    stub — the window ceiling it normally wraps around is exercised in
    ``test_zalo_window_notifier.py``, not here. Stubbing the factory also
    keeps this module's subject intact: which branch fires, and what it
    says.
    """
    zalo = _SpyNotifier()
    telegram = _SpyNotifier()

    monkeypatch.setattr(
        zalo_inbound, "build_zalo_notifier", lambda zalo_user_id, **kwargs: zalo
    )
    monkeypatch.setattr(zalo_inbound, "get_notifier", lambda: telegram)
    return zalo, telegram


class _OnboardingSpy:
    """Stands in for ``zalo_onboarding`` so this module keeps its subject.

    Phase 5.1 #4.3 put onboarding in front of dispatch: a stranger is
    signed up, and a known sender's text is offered to the step machine
    before the intent stack sees it. What that machine *says* is tested
    against the real services in ``tests/test_phase_5_1``; what this
    module still owns is which branch of the handler fires, so both
    entry points are stubbed to the quiet answer — "signed them up" and
    "not mine, carry on".
    """

    def __init__(self) -> None:
        self.signed_up: list[str] = []
        self.offered: list[str] = []
        self.new_user = _FakeUser(telegram_id=None)
        self.claims_text = False

    async def start_new_user(self, db, *, notifier, zalo_user_id):
        self.signed_up.append(zalo_user_id)
        return self.new_user

    async def handle_text(self, db, *, notifier, user, text):
        self.offered.append(text)
        return self.claims_text


@pytest.fixture(autouse=True)
def onboarding(monkeypatch):
    spy = _OnboardingSpy()
    module = zalo_inbound.zalo_onboarding
    monkeypatch.setattr(module, "start_new_user", spy.start_new_user)
    monkeypatch.setattr(module, "handle_text", spy.handle_text)
    return spy


@pytest.fixture()
def zalo_out(_isolate_channel):
    return _isolate_channel[0]


@pytest.fixture()
def telegram_out(_isolate_channel):
    return _isolate_channel[1]


def _stub_service(monkeypatch, *, linked=None, redemption=None, user=None):
    async def _get_linked_user(db, zalo_user_id):
        return linked

    async def _redeem(db, token, zalo_user_id):
        return redemption

    async def _get_user_by_id(db, user_id):
        return user

    service = zalo_inbound.zalo_linking_service
    monkeypatch.setattr(service, "get_linked_user", _get_linked_user)
    monkeypatch.setattr(service, "redeem_link_token", _redeem)
    monkeypatch.setattr(service, "get_user_by_id", _get_user_by_id)


# --------------------------------------------------------------------------
# Token branch
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_token_links_and_confirms_on_both_channels(
    monkeypatch, zalo_out, telegram_out
):
    user = _FakeUser()
    _stub_service(
        monkeypatch,
        redemption=LinkRedemption(status="linked", user_id=user.id),
        user=user,
    )

    result = await zalo_inbound.handle_inbound_event(
        _SpySession(), event=_event(f"mã của tôi: {TOKEN} nhé")
    )

    assert result == user.id
    assert len(zalo_out.sent) == 1
    assert "kết nối thành công" in zalo_out.sent[0][1]
    assert telegram_out.sent == [(555, zalo_copy.linking("confirm_telegram"))]


@pytest.mark.asyncio
async def test_relink_is_treated_as_a_successful_link(monkeypatch, zalo_out):
    user = _FakeUser()
    _stub_service(
        monkeypatch,
        redemption=LinkRedemption(
            status="user_relinked", user_id=user.id, previous_zalo_user_id="old"
        ),
        user=user,
    )

    result = await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(TOKEN))

    assert result == user.id
    assert len(zalo_out.sent) == 1


@pytest.mark.asyncio
async def test_zalo_only_account_still_gets_its_confirmation(
    monkeypatch, zalo_out, telegram_out
):
    """No Telegram side to confirm on is not an error — the Zalo
    confirmation already went out."""
    user = _FakeUser(telegram_id=None)
    _stub_service(
        monkeypatch,
        redemption=LinkRedemption(status="linked", user_id=user.id),
        user=user,
    )

    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(TOKEN))

    assert len(zalo_out.sent) == 1
    assert telegram_out.sent == []


@pytest.mark.parametrize(
    ("status", "marker"),
    [
        ("already_used", "đã được dùng rồi"),
        ("expired", "đã hết hạn"),
        ("invalid", "không hợp lệ"),
        ("some_future_status", "không hợp lệ"),
    ],
)
@pytest.mark.asyncio
async def test_failed_redemption_explains_itself(monkeypatch, zalo_out, status, marker):
    """Each failure mode gets copy the user can act on — an unknown
    status falls back to the generic nudge rather than going silent."""
    _stub_service(monkeypatch, redemption=LinkRedemption(status=status))

    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(TOKEN))

    assert len(zalo_out.sent) == 1
    assert marker in zalo_out.sent[0][1]


@pytest.mark.asyncio
async def test_failed_redemption_keeps_the_existing_binding_for_audit(monkeypatch):
    """A linked sender who pastes a stale code is still that user — the
    ``zalo_updates`` row must not lose its ``user_id``."""
    linked = _FakeUser()
    _stub_service(
        monkeypatch, linked=linked, redemption=LinkRedemption(status="expired")
    )

    result = await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(TOKEN))

    assert result == linked.id


@pytest.mark.asyncio
async def test_redemption_log_never_carries_the_token_or_sender(monkeypatch, caplog):
    _stub_service(monkeypatch, redemption=LinkRedemption(status="invalid"))

    with caplog.at_level(logging.DEBUG):
        await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(TOKEN))

    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert "link_redemption status=invalid" in blob
    assert TOKEN not in blob
    assert SENDER_ID not in blob


# --------------------------------------------------------------------------
# Linked / unlinked branches
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linked_sender_is_never_left_without_an_answer(
    monkeypatch, zalo_out, install_intent_stack
):
    linked = _FakeUser()
    _stub_service(monkeypatch, linked=linked)
    install_intent_stack()

    result = await zalo_inbound.handle_inbound_event(
        _SpySession(), event=_event("ăn trưa 50k")
    )

    assert result == linked.id
    assert len(zalo_out.sent) == 1


@pytest.mark.asyncio
async def test_an_unlinked_sender_is_signed_up_rather_than_nudged(
    monkeypatch, onboarding
):
    """#4.3 replaced the "/link_zalo" nudge with a signup.

    Answering "go fetch a code from Telegram" to someone whose only
    channel is Zalo was a dead end, so the branch now mints an account
    and hands the sender to onboarding. The update row still gets a user
    id — the new one.
    """
    _stub_service(monkeypatch, linked=None)

    result = await zalo_inbound.handle_inbound_event(
        _SpySession(), event=_event("xin chào")
    )

    assert onboarding.signed_up == [SENDER_ID]
    assert result == onboarding.new_user.id


@pytest.mark.asyncio
async def test_a_known_sender_is_offered_to_onboarding_before_dispatch(
    monkeypatch, onboarding, install_intent_stack
):
    """Order matters: an answer to "Bé Tiền gọi anh là gì?" must not be
    read as a transaction. Onboarding declines here, so dispatch runs."""
    _stub_service(monkeypatch, linked=_FakeUser())
    _, dispatcher = install_intent_stack()

    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event("ăn trưa 50k"))

    assert onboarding.offered == ["ăn trưa 50k"]
    assert dispatcher.calls


@pytest.mark.asyncio
async def test_text_onboarding_claims_never_reaches_the_intent_stack(
    monkeypatch, onboarding, install_intent_stack
):
    linked = _FakeUser()
    _stub_service(monkeypatch, linked=linked)
    _, dispatcher = install_intent_stack()
    onboarding.claims_text = True

    result = await zalo_inbound.handle_inbound_event(
        _SpySession(), event=_event("Phương")
    )

    assert result == linked.id
    assert dispatcher.calls == []


# --------------------------------------------------------------------------
# Suspension gate (#5)
# --------------------------------------------------------------------------
#
# Telegram refuses a suspended account at its worker. Without the same
# refusal here, Zalo would be the way *around* the suspension — which is
# the only reason these tests care about a second channel at all.


@pytest.mark.asyncio
async def test_suspended_sender_is_answered_but_never_dispatched(
    monkeypatch, zalo_out, install_intent_stack
):
    linked = _FakeUser()
    _stub_service(monkeypatch, linked=linked)
    pipeline, dispatcher = install_intent_stack()

    result = await zalo_inbound.handle_inbound_event(
        _SpySession(manual_status=STATUS_SUSPENDED), event=_event("ăn trưa 50k")
    )

    # Not classified either: the gate sits before the LLM, so a suspended
    # account can't spend the classifier budget by messaging in a loop.
    assert pipeline.texts == []
    assert dispatcher.calls == []
    assert zalo_out.sent == [(0, zalo_copy.text("account", "suspended"))]
    # The row still learns who sent it. An audit trail that stops at the
    # gate is the one you need when the suspension is disputed.
    assert result == linked.id


@pytest.mark.asyncio
async def test_suspended_account_cannot_relink_its_way_past_the_gate(
    monkeypatch, zalo_out, telegram_out
):
    """The token branch is checked too — a fresh code must not act as a
    reset. Redemption itself still runs (the binding is useful the moment
    an admin lifts the suspension); what is withheld is the confirmation
    promising a channel that will refuse the next message."""
    user = _FakeUser()
    _stub_service(
        monkeypatch,
        redemption=LinkRedemption(status="linked", user_id=user.id),
        user=user,
    )

    result = await zalo_inbound.handle_inbound_event(
        _SpySession(manual_status=STATUS_SUSPENDED), event=_event(TOKEN)
    )

    assert result == user.id
    assert zalo_out.sent == [(0, zalo_copy.text("account", "suspended"))]
    assert telegram_out.sent == []


@pytest.mark.asyncio
async def test_an_unlinked_suspended_sender_is_still_signed_up(monkeypatch, onboarding):
    """Nobody to suspend yet: with no binding there is no account to look
    up, so the gate must not fire — and must not cost a query either.

    ``manual_status`` here belongs to whatever the fake session would
    answer, not to this sender; #4.3 gives them a fresh account, and a
    fresh account is never suspended.
    """
    _stub_service(monkeypatch, linked=None)
    db = _SpySession(manual_status=STATUS_SUSPENDED)

    result = await zalo_inbound.handle_inbound_event(db, event=_event("xin chào"))

    assert db.scalars_read == 0
    assert onboarding.signed_up == [SENDER_ID]
    assert result == onboarding.new_user.id


@pytest.mark.asyncio
async def test_active_account_passes_the_gate_at_the_cost_of_one_read(
    monkeypatch, zalo_out, install_intent_stack
):
    """Pins the price of the gate on the hot path: a single scalar read,
    on the same session the worker already opened."""
    _stub_service(monkeypatch, linked=_FakeUser())
    _, dispatcher = install_intent_stack()
    db = _SpySession(manual_status=STATUS_ACTIVE)

    await zalo_inbound.handle_inbound_event(db, event=_event("ăn trưa 50k"))

    assert db.scalars_read == 1
    assert len(dispatcher.calls) == 1


@pytest.mark.asyncio
async def test_suspension_notice_never_names_the_sender_or_the_reason(
    monkeypatch, zalo_out, caplog
):
    """The handler doesn't know *why* an admin suspended the account, so
    the bubble points at a human instead of guessing — and the log keeps
    its hands off the sender id like every other line here."""
    _stub_service(monkeypatch, linked=_FakeUser())

    with caplog.at_level(logging.DEBUG):
        await zalo_inbound.handle_inbound_event(
            _SpySession(manual_status=STATUS_SUSPENDED), event=_event("ăn trưa 50k")
        )

    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert "account suspended" in blob
    assert SENDER_ID not in blob

    body = zalo_out.sent[0][1]
    # Copy lives in content/zalo.yaml, never inline — a missing key would
    # degrade to the raw marker, which this catches.
    assert "account.suspended" not in body
    assert "tạm khoá" in body


# --------------------------------------------------------------------------
# Dispatch (#2.3, widened to every intent in #4.1)
# --------------------------------------------------------------------------


async def _dispatch(monkeypatch, text: str = "ăn trưa 50k"):
    """Drive one message from a linked sender through the handler."""
    linked = _FakeUser()
    _stub_service(monkeypatch, linked=linked)
    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(text))
    return linked


@pytest.mark.asyncio
async def test_a_served_message_is_dispatched_and_its_answer_sent(
    monkeypatch, zalo_out, install_intent_stack
):
    pipeline, dispatcher = install_intent_stack(
        intent=IntentType.QUERY_EXPENSES,
        outcome=DispatchOutcome(
            text="Tháng 8 bạn đã chi 1,200,000đ.",
            kind=OUTCOME_EXECUTED,
            intent=IntentType.QUERY_EXPENSES,
            confidence=0.95,
        ),
    )

    linked = await _dispatch(monkeypatch, "tháng này tiêu bao nhiêu")

    assert pipeline.texts == ["tháng này tiêu bao nhiêu"]
    # The dispatcher gets the *same* user the linking service resolved —
    # a mismatch here would answer one account with another's numbers.
    assert [call[1] for call in dispatcher.calls] == [linked]
    assert zalo_out.sent == [(0, "Tháng 8 bạn đã chi 1,200,000đ.")]


@pytest.mark.asyncio
async def test_self_sending_handler_is_not_echoed(
    monkeypatch, zalo_out, install_intent_stack
):
    """``action_quick_transaction`` sends its own confirmation and returns
    an empty string. #2.4 made that send channel-aware, so the Zalo
    bubble has already gone out — a second send here would show the user
    the same transaction twice."""
    install_intent_stack(
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        outcome=DispatchOutcome(
            text="",
            kind=OUTCOME_EXECUTED,
            intent=IntentType.ACTION_QUICK_TRANSACTION,
            confidence=0.95,
        ),
    )

    await _dispatch(monkeypatch)

    assert zalo_out.sent == []


@pytest.mark.asyncio
async def test_a_wizard_intent_never_reaches_the_dispatcher(
    monkeypatch, zalo_out, install_intent_stack
):
    """A wizard handler pushes a Telegram keyboard and returns ``""``.
    Run from Zalo it would answer the wrong channel — or, for a Zalo-only
    account since #4.2, send to ``chat_id=None``. The check runs *before*
    dispatch, so it costs no handler run and can have no side effects.

    High confidence on purpose: this is the wizard rule firing on its own,
    not the flow-state rule catching it on the way past.
    """
    _, dispatcher = install_intent_stack(
        intent=IntentType.ACTION_ADD_ASSET, confidence=0.99
    )

    await _dispatch(monkeypatch, "thêm tài sản nhà 3 tỷ")

    assert dispatcher.calls == []
    assert zalo_out.sent == [(0, zalo_copy.text("fallback", "unsupported"))]


@pytest.mark.asyncio
async def test_low_confidence_short_circuits_before_the_dispatcher(
    monkeypatch, zalo_out, install_intent_stack
):
    """Below ``CONFIRM_THRESHOLD`` the dispatcher would persist Telegram
    flow state that only ``free_form_text`` can consume — a Zalo message
    must never arm it, or the user gets ambushed by a reply to a question
    they were asked on another channel."""
    _, dispatcher = install_intent_stack(
        intent=IntentType.QUERY_EXPENSES, confidence=CONFIRM_THRESHOLD - 0.01
    )

    await _dispatch(monkeypatch, "ừm")

    assert dispatcher.calls == []
    assert zalo_out.sent == [(0, zalo_copy.text("fallback", "unclear"))]


@pytest.mark.asyncio
async def test_a_medium_confidence_write_intent_is_held_back(
    monkeypatch, zalo_out, install_intent_stack
):
    """The other half of the flow-state rule, and the one a threshold
    check alone would miss: above ``CONFIRM_THRESHOLD`` but below execute,
    a write intent takes the dispatcher's *confirm* branch, which calls
    ``set_pending_action``. Also on Zalo's side of the wall."""
    _, dispatcher = install_intent_stack(
        intent=IntentType.ACTION_RECORD_SAVING, confidence=CONFIRM_THRESHOLD + 0.01
    )

    await _dispatch(monkeypatch, "để dành 2 triệu")

    assert dispatcher.calls == []
    assert zalo_out.sent == [(0, zalo_copy.text("fallback", "unclear"))]


@pytest.mark.asyncio
async def test_exactly_at_the_threshold_still_dispatches(
    monkeypatch, zalo_out, install_intent_stack
):
    """Boundary pinned explicitly: ``>=``, not ``>``. A read intent at
    exactly ``CONFIRM_THRESHOLD`` executes rather than clarifying, so it
    persists nothing and Zalo can serve it."""
    _, dispatcher = install_intent_stack(
        intent=IntentType.QUERY_EXPENSES, confidence=CONFIRM_THRESHOLD
    )

    await _dispatch(monkeypatch, "tháng này tiêu bao nhiêu")

    assert len(dispatcher.calls) == 1


@pytest.mark.parametrize("failure", ["classify", "dispatch"])
@pytest.mark.asyncio
async def test_a_failure_answers_with_the_fallback_instead_of_raising(
    monkeypatch, zalo_out, install_intent_stack, failure
):
    """A raise would mark the ``zalo_updates`` row ``failed``; orphan
    recovery would then replay the message and could record the same
    transaction twice — while the user saw nothing at all."""
    boom = RuntimeError("classifier timed out")
    install_intent_stack(
        classify_error=boom if failure == "classify" else None,
        dispatch_error=boom if failure == "dispatch" else None,
    )

    await _dispatch(monkeypatch)

    assert zalo_out.sent == [(0, zalo_copy.text("fallback", "body"))]


@pytest.mark.asyncio
async def test_button_spans_are_unwrapped_not_left_as_dead_labels(
    monkeypatch, zalo_out, install_intent_stack
):
    """``[Xem chi tiết]`` is Telegram's inline-button markup. Zalo has no
    buttons in 5.0, and the brackets would read as something tappable."""
    install_intent_stack(
        intent=IntentType.QUERY_NET_WORTH,
        outcome=DispatchOutcome(
            text="Tổng tài sản 1 tỷ 200.\n[Xem chi tiết]  [Bỏ qua]",
            kind=OUTCOME_EXECUTED,
            intent=IntentType.QUERY_NET_WORTH,
            confidence=0.9,
        ),
    )

    await _dispatch(monkeypatch, "tài sản của tôi")

    body = zalo_out.sent[0][1]
    assert "[" not in body and "]" not in body
    # Unwrapped, not deleted — the label carries the only verb.
    assert body == "Tổng tài sản 1 tỷ 200.\nXem chi tiết Bỏ qua"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[Xem báo cáo]", "Xem báo cáo"),
        ("Chọn:\n[A]  [B]", "Chọn:\nA B"),
        ("[A]\n\n[B]", "A\nB"),
        ("không có nút", "không có nút"),
    ],
)
def test_plain_body_collapses_the_whitespace_unwrapping_creates(raw, expected):
    assert zalo_inbound._plain_body(raw) == expected


def test_a_markdown_link_loses_its_url_rather_than_stranding_it():
    # The ordering guarantee, as a test: the link is unwrapped *before*
    # the bare-bracket pass runs. Reversed, the brackets would go first
    # and "(https://x.vn)" would survive into the bubble as visible noise
    # pointing at a page the reader cannot open from a Zalo chat.
    assert zalo_inbound._plain_body("xem tại [đây](https://x.vn)") == "xem tại đây"


@pytest.mark.asyncio
async def test_dispatch_telemetry_never_carries_the_message_or_sender(
    monkeypatch, caplog, install_intent_stack
):
    """The log line and the analytics event are both intent-shaped: what
    was classified and how confidently, never what the user typed."""
    events: list[tuple] = []
    monkeypatch.setattr(
        zalo_inbound.analytics,
        "track",
        lambda name, user_id=None, properties=None: events.append(
            (name, user_id, properties)
        ),
    )
    install_intent_stack(intent=IntentType.QUERY_EXPENSES)
    secret = "chuyển 5 triệu cho chị Lan"

    with caplog.at_level(logging.DEBUG):
        linked = await _dispatch(monkeypatch, secret)

    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert "intent=query_expenses" in blob
    assert secret not in blob
    assert SENDER_ID not in blob

    (name, user_id, properties) = events[0]
    # Same event name as the Telegram path so the funnel stays one series.
    assert name == "intent_classified"
    assert user_id == linked.id
    assert properties["channel"] == "zalo"
    assert properties["intent"] == "query_expenses"
    assert secret not in str(properties)
    assert SENDER_ID not in str(properties)


def test_nothing_that_arms_telegram_flow_state_is_served():
    """The invariant the whitelist used to enforce, now asserted directly
    against the blocklist for *every* intent rather than for the seven
    that happened to be listed.

    The two dangerous classes are the confirm branch (``set_pending_action``)
    and the clarify branch (``set_awaiting_clarification``). Both are
    ``free_form_text``'s to consume, so both must come back unserved.
    """
    confirm_requiring = (
        WRITE_INTENTS
        - {IntentType.ACTION_QUICK_TRANSACTION}
        - set(WIZARD_LAUNCHING_INTENTS)
    )
    for intent in confirm_requiring:
        result = _result(intent, CONFIRM_THRESHOLD + 0.01)
        assert zalo_inbound._unserved_reason(result) is not None, (
            f"would persist a pending action on Zalo: {intent}"
        )

    for intent in WIZARD_LAUNCHING_INTENTS:
        result = _result(intent, 0.99)
        assert zalo_inbound._unserved_reason(result) == zalo_inbound.REASON_WIZARD, (
            f"would launch a Telegram-only wizard on Zalo: {intent}"
        )

    # The one low-confidence case that *is* served, and deliberately so:
    # ``UNCLEAR`` has no original intent to come back to, so the dispatcher
    # answers from a static template and persists nothing. Holding it back
    # would swap Bé Tiền's own "chưa hiểu ý bạn" for the generic fallback
    # — strictly worse copy for no safety gained.
    unclear = _result(IntentType.UNCLEAR, 0.99)
    assert zalo_inbound._unserved_reason(unclear) is None


def test_every_unserved_reason_has_its_own_copy():
    """A reason with no entry in the map would raise ``KeyError`` mid-send
    and leave the user with silence — the one outcome the fallback exists
    to prevent. Copy itself is checked by the zalo.yaml scanners."""
    reasons = {
        zalo_inbound.REASON_WIZARD,
        zalo_inbound.REASON_FLOW_STATE,
        zalo_inbound.REASON_ERROR,
    }
    assert set(zalo_inbound._REASON_COPY) == reasons
    for key in zalo_inbound._REASON_COPY.values():
        assert zalo_copy.text("fallback", key).strip()


# --------------------------------------------------------------------------
# Nothing to act on
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_text_event_is_ignored(monkeypatch, zalo_out):
    _stub_service(monkeypatch, linked=_FakeUser())

    result = await zalo_inbound.handle_inbound_event(
        _SpySession(), event=_event("", event_name="follow")
    )

    assert result is None
    assert zalo_out.sent == []


@pytest.mark.asyncio
async def test_whitespace_only_message_gets_no_reply(monkeypatch, zalo_out):
    """A sticker or attachment-only message has nothing to act on.
    Silence beats an error the user didn't ask for."""
    _stub_service(monkeypatch, linked=_FakeUser())

    result = await zalo_inbound.handle_inbound_event(_SpySession(), event=_event("   "))

    assert result is None
    assert zalo_out.sent == []


# --------------------------------------------------------------------------
# Copy loader
# --------------------------------------------------------------------------


def test_missing_copy_key_degrades_instead_of_raising(caplog):
    """A copy gap must never crash a background task — the inbound
    message would be lost with it."""
    with caplog.at_level(logging.WARNING):
        assert zalo_copy.text("linking", "no_such_key") == ""

    assert "zalo.copy missing string" in "\n".join(
        r.getMessage() for r in caplog.records
    )


def test_unformattable_template_falls_back_to_the_raw_string(caplog):
    with caplog.at_level(logging.WARNING):
        out = zalo_copy.linking("prompt", wrong_placeholder="x")

    assert "{token}" in out
