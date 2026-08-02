"""Phase 5.0 #2.2 + #2.3 — the inbound handler's routing decisions.

One branch per message, and each branch has a user-visible consequence:

* a pasted ``BT-XXXXXX`` code links the account and confirms on *both*
  channels (the code was issued in Telegram — the loop closes where the
  user started it);
* a linked sender gets their message classified and answered — inside the
  thin slice for real, outside it with an invitation to Telegram;
* an unlinked sender gets the linking nudge rather than a dead end.

Also pins the things that must never happen: no ``db.commit()`` from the
handler (the worker owns the boundary), no token, sender id or message
text in the logs, and no dispatch of an intent the thin slice excludes.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from backend.bot.handlers import zalo_inbound
from backend.intent.dispatcher import (
    CONFIRM_THRESHOLD,
    OUTCOME_EXECUTED,
    WRITE_INTENTS,
    DispatchOutcome,
    _WIZARD_LAUNCHING_INTENTS,
)
from backend.intent.intents import IntentType
from backend.services.user_status import STATUS_ACTIVE, STATUS_SUSPENDED
from backend.services.zalo_linking_service import LinkRedemption
from backend.utils import zalo_copy
from backend.utils.zalo_events import ZaloEvent

SENDER_ID = "zalo-sender-should-never-be-logged"
TOKEN = "BT-ABC234"


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
async def test_unlinked_sender_gets_the_linking_nudge(monkeypatch, zalo_out):
    _stub_service(monkeypatch, linked=None)

    result = await zalo_inbound.handle_inbound_event(
        _SpySession(), event=_event("xin chào")
    )

    assert result is None
    assert "/link_zalo" in zalo_out.sent[0][1]


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
async def test_an_unlinked_suspended_sender_still_gets_the_linking_nudge(
    monkeypatch, zalo_out
):
    """Nobody to suspend yet: with no binding there is no account to look
    up, so the gate must not fire — and must not cost a query either."""
    _stub_service(monkeypatch, linked=None)
    db = _SpySession(manual_status=STATUS_SUSPENDED)

    result = await zalo_inbound.handle_inbound_event(db, event=_event("xin chào"))

    assert result is None
    assert db.scalars_read == 0
    assert "/link_zalo" in zalo_out.sent[0][1]


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
# Thin-slice dispatch (#2.3)
# --------------------------------------------------------------------------


async def _dispatch(monkeypatch, text: str = "ăn trưa 50k"):
    """Drive one message from a linked sender through the handler."""
    linked = _FakeUser()
    _stub_service(monkeypatch, linked=linked)
    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(text))
    return linked


@pytest.mark.asyncio
async def test_in_slice_message_is_dispatched_and_its_answer_sent(
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
async def test_out_of_slice_intent_never_reaches_the_dispatcher(
    monkeypatch, zalo_out, install_intent_stack
):
    """The whitelist is checked *before* dispatch, so an out-of-slice
    intent costs no handler run and — the point — can have no side
    effects."""
    _, dispatcher = install_intent_stack(
        intent=IntentType.ACTION_ADD_ASSET, confidence=0.99
    )

    await _dispatch(monkeypatch, "thêm tài sản nhà 3 tỷ")

    assert dispatcher.calls == []
    assert zalo_out.sent == [(0, zalo_copy.text("fallback", "body"))]


@pytest.mark.asyncio
async def test_low_confidence_short_circuits_before_the_dispatcher(
    monkeypatch, zalo_out, install_intent_stack
):
    """Below ``CONFIRM_THRESHOLD`` the dispatcher would persist Telegram
    flow state that only ``free_form_text`` can consume — a Zalo message
    must never arm it."""
    _, dispatcher = install_intent_stack(
        intent=IntentType.QUERY_EXPENSES, confidence=CONFIRM_THRESHOLD - 0.01
    )

    await _dispatch(monkeypatch, "ừm")

    assert dispatcher.calls == []
    assert zalo_out.sent == [(0, zalo_copy.text("fallback", "body"))]


@pytest.mark.asyncio
async def test_exactly_at_the_threshold_still_dispatches(
    monkeypatch, zalo_out, install_intent_stack
):
    """Boundary pinned explicitly: ``>=``, not ``>``. The dispatcher's own
    confirm branch uses the same comparison, so an off-by-one here would
    silently shrink the slice."""
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


def test_the_whitelist_cannot_arm_telegram_flow_state():
    """The invariant behind the whitelist, asserted against the
    dispatcher's own tables rather than restated by hand.

    Every whitelisted intent must be one the dispatcher *executes* at
    ``CONFIRM_THRESHOLD``: no confirm branch (which persists a pending
    action), no wizard (which persists a multi-step Telegram state).
    Adding an intent that breaks either property fails here.
    """
    confirm_requiring = (
        WRITE_INTENTS
        - {IntentType.ACTION_QUICK_TRANSACTION}
        - set(_WIZARD_LAUNCHING_INTENTS)
    )
    offenders = zalo_inbound.ZALO_SUPPORTED_INTENTS & confirm_requiring
    assert not offenders, f"would persist a pending action on Zalo: {offenders}"

    wizards = zalo_inbound.ZALO_SUPPORTED_INTENTS & set(_WIZARD_LAUNCHING_INTENTS)
    assert not wizards, f"would launch a Telegram-only wizard on Zalo: {wizards}"

    assert IntentType.UNCLEAR not in zalo_inbound.ZALO_SUPPORTED_INTENTS


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
