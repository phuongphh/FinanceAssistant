"""The 48h/8-message ceiling, enforced at the notifier seam (#3.2).

What these tests are really guarding is one sentence of the DoD:
*"Ngoài cửa sổ 48h hoặc đã dùng 8 tin → không gọi ``/message/cs``,
Telegram vẫn nhận, log rõ lý do."* Three claims, each of which fails in a
different, quiet way if it regresses:

* **không gọi** — a blocked send must not reach the OA client at all. So
  every refusal test asserts on ``client.sent`` being empty, not merely
  on the return value. A wrapper that called Zalo and then discarded the
  result would satisfy a return-value assertion and still burn quota.
* **Telegram vẫn nhận** — a block returns ``None``, the same value a
  transport failure returns, because that is what every caller already
  reads as "this channel didn't take it" before falling through.
* **log rõ lý do** — the reason is one of the service's stable strings
  and the sender id never appears verbatim.

Two things are deliberately *not* asserted here. The atomicity of
``UPDATE ... WHERE free_msg_count < 8`` is a Postgres property, pinned by
the compiled-SQL tests in ``test_zalo_window_service.py``;
``FakeWindowStore`` does not model row locking. And the copy of any
message is not this file's business — the wrapper is transparent to it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import pytest

from backend.adapters import zalo_window_notifier as mod
from backend.adapters.zalo_notifier import ZaloNotifier
from backend.adapters.zalo_oa import ZaloSendRejected
from backend.adapters.zalo_window_notifier import (
    WindowedZaloNotifier,
    build_zalo_notifier,
)
from backend.models.zalo_message_window import FREE_MESSAGE_QUOTA
from backend.services import zalo_window_service as svc

SENDER = "zalo-sender-should-never-be-logged"
LOGGER_NAME = "backend.adapters.zalo_window_notifier"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeOAClient:
    """Records what reached the transport, and how far the ledger had got.

    ``commits_seen`` is the interesting field: it snapshots the store's
    commit count *at the moment of the call*, which is the only way to
    assert the reservation was durable **before** the send rather than
    merely flushed alongside it. That ordering is the whole quota
    guarantee — an uncommitted reservation is invisible to every other
    worker.
    """

    is_configured = True
    # The resolver checks the channel flag before the credential (#2):
    # credentials outlive ``ZALO_CHANNEL_ENABLED=false`` on purpose, so
    # the flag has to be the thing that gates fan-out.
    is_send_enabled = True

    def __init__(self, store, *, ok: bool = True, error: Exception | None = None):
        self._store = store
        self._ok = ok
        self._error = error
        self.sent: list[tuple[str, str]] = []
        self.images: list[tuple[str, str, str]] = []
        self.commits_seen: list[int] = []

    async def send_message(self, recipient_id: str, text: str) -> bool:
        self.commits_seen.append(self._store.commits)
        self.sent.append((recipient_id, text))
        if self._error is not None:
            raise self._error
        return self._ok

    async def send_image_message(
        self, recipient_id: str, image_url: str, caption: str = ""
    ) -> bool:
        self.commits_seen.append(self._store.commits)
        self.images.append((recipient_id, image_url, caption))
        if self._error is not None:
            raise self._error
        return self._ok


def session_factory_for(store, *, fail_on_open: set[int] | None = None):
    """A stand-in for ``get_session_factory()`` over one in-memory store.

    Every send opens its own session in production; here they all land on
    the same store, which is what makes "two sends, one ledger" testable.
    ``fail_on_open`` lets a test break the *n*-th session open, to check
    that a compensation failure can't turn a delivery failure into a
    stack trace.
    """
    state = {"opens": 0}

    @contextlib.asynccontextmanager
    async def _open():
        state["opens"] += 1
        if fail_on_open and state["opens"] in fail_on_open:
            raise RuntimeError("connection pool exhausted")
        yield store

    def factory():
        return _open()

    factory.state = state
    return factory


def notifier_for(store, client) -> WindowedZaloNotifier:
    return WindowedZaloNotifier(
        ZaloNotifier(client=client, zalo_user_id=SENDER),
        SENDER,
        session_factory=session_factory_for(store),
    )


async def open_window(store, *, used: int = 0) -> None:
    """Put the store in "user messaged us, ``used`` replies spent" state."""
    await svc.record_inbound(store, zalo_user_id=SENDER)
    store.rows[SENDER].free_msg_count = used


# ---------------------------------------------------------------------------
# The allowed path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_send_inside_the_window_reaches_zalo_and_spends_one_slot(window_store):
    await open_window(window_store)
    client = FakeOAClient(window_store)

    result = await notifier_for(window_store, client).send_message(0, "Đã ghi 50k")

    assert result == {"ok": True, "channel": "zalo"}
    assert client.sent == [(SENDER, "Đã ghi 50k")]
    assert window_store.rows[SENDER].free_msg_count == 1


@pytest.mark.asyncio
async def test_the_reservation_is_committed_before_the_transport_call(window_store):
    """Not a style point — it is the ceiling.

    A reservation that is only flushed holds a row lock and is invisible
    to every other worker, so eight concurrent sends would each read the
    same stale count and each deliver. The commit has to have happened by
    the time the OA call goes out.
    """
    await open_window(window_store)
    client = FakeOAClient(window_store)

    await notifier_for(window_store, client).send_message(0, "xin chào")

    assert client.commits_seen == [1]
    # …and the reserve landed before that commit, not after it.
    assert window_store.events[: window_store.events.index("commit")] == [
        "record_inbound",
        "reserve",
    ]


@pytest.mark.asyncio
async def test_all_eight_free_messages_are_usable(window_store):
    """The ceiling is eight, not seven — an off-by-one here costs a reply."""
    await open_window(window_store)
    client = FakeOAClient(window_store)
    notifier = notifier_for(window_store, client)

    results = [await notifier.send_message(0, f"tin {i}") for i in range(9)]

    assert [r is not None for r in results] == [True] * FREE_MESSAGE_QUOTA + [False]
    assert len(client.sent) == FREE_MESSAGE_QUOTA


# ---------------------------------------------------------------------------
# The blocked paths — "không gọi /message/cs"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_sender_who_never_messaged_us_is_never_messaged(window_store):
    """No window row at all: the OA never followed, or we cold-started.

    Zalo would reject this outright, and a rejection still costs a
    round-trip on a path a user is waiting on.
    """
    client = FakeOAClient(window_store)

    result = await notifier_for(window_store, client).send_message(0, "briefing")

    assert result is None
    assert client.sent == []


@pytest.mark.asyncio
async def test_an_expired_window_blocks_the_send(window_store):
    await open_window(window_store)
    # 48h and a second later — the window the inbound message opened has
    # lapsed without a new one replacing it.
    row = window_store.rows[SENDER]
    row.window_expires_at = row.window_expires_at.replace(year=2020)
    client = FakeOAClient(window_store)

    result = await notifier_for(window_store, client).send_message(0, "briefing")

    assert result is None
    assert client.sent == []
    # No slot was spent on a message that was never attempted.
    assert row.free_msg_count == 0


@pytest.mark.asyncio
async def test_the_ninth_message_in_one_window_blocks(window_store):
    await open_window(window_store, used=FREE_MESSAGE_QUOTA)
    client = FakeOAClient(window_store)

    result = await notifier_for(window_store, client).send_message(0, "tin thứ 9")

    assert result is None
    assert client.sent == []
    assert window_store.rows[SENDER].free_msg_count == FREE_MESSAGE_QUOTA


@pytest.mark.asyncio
async def test_a_new_inbound_message_reopens_the_allowance(window_store):
    """The quota is per window, not per day: replying is possible again."""
    await open_window(window_store, used=FREE_MESSAGE_QUOTA)
    client = FakeOAClient(window_store)
    notifier = notifier_for(window_store, client)

    assert await notifier.send_message(0, "chặn") is None

    await svc.record_inbound(window_store, zalo_user_id=SENDER)

    assert await notifier.send_message(0, "trả lời") is not None
    assert client.sent == [(SENDER, "trả lời")]


@pytest.mark.asyncio
async def test_the_block_reason_is_logged_without_the_sender_id(window_store, caplog):
    """*"log rõ lý do"* — with the emphasis on *lý do*, not on *ai*.

    The reason string comes from the service's stable constants so #3.3
    can lift it straight into a counter label. The Zalo id is
    pseudonymous but still identifies a person, so it is masked with the
    same rule the service uses — two lines about the same sender still
    join up, neither one can address them.

    One reason is enough here; the per-reason sweep lives in
    ``test_every_refusal_reason_reaches_the_log_verbatim``.
    """
    await open_window(window_store, used=FREE_MESSAGE_QUOTA)
    client = FakeOAClient(window_store)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await notifier_for(window_store, client).send_message(0, "chặn")

    blocked = [r for r in caplog.records if "zalo.send.blocked" in r.getMessage()]
    assert len(blocked) == 1
    message = blocked[0].getMessage()
    assert f"reason={svc.REASON_QUOTA_EXHAUSTED}" in message
    assert "kind=text" in message
    assert SENDER not in message
    assert svc.mask_zalo_id(SENDER) in message


@pytest.mark.asyncio
async def test_every_refusal_reason_reaches_the_log_verbatim(window_store, caplog):
    """One case per reason, so a renamed constant can't slip through.

    Renaming one of these silently retires a dashboard panel, which is
    the kind of breakage nothing else in the suite would notice.
    """
    client = FakeOAClient(window_store)
    notifier = notifier_for(window_store, client)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await notifier.send_message(0, "không có cửa sổ")

        await open_window(window_store)
        row = window_store.rows[SENDER]
        row.window_expires_at = row.window_expires_at.replace(year=2020)
        await notifier.send_message(0, "cửa sổ đóng")

        await open_window(window_store, used=FREE_MESSAGE_QUOTA)
        await notifier.send_message(0, "hết lượt")

    reasons = [
        r.getMessage().split("reason=")[1].split(" ")[0]
        for r in caplog.records
        if "zalo.send.blocked" in r.getMessage()
    ]
    assert reasons == [
        svc.REASON_NO_WINDOW,
        svc.REASON_WINDOW_CLOSED,
        svc.REASON_QUOTA_EXHAUSTED,
    ]
    assert client.sent == []


@pytest.mark.asyncio
async def test_the_users_own_words_never_reach_a_log_line(window_store, caplog):
    await open_window(window_store, used=FREE_MESSAGE_QUOTA)
    secret = "chuyển 20tr cho chị Hà tiền viện phí"

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        await notifier_for(window_store, FakeOAClient(window_store)).send_message(
            0, secret
        )

    assert all(secret not in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Messages that were never going to be sent cost nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "**__**", "`` ``", "<b></b>"])
@pytest.mark.asyncio
async def test_a_body_that_renders_to_nothing_costs_no_slot(window_store, text):
    """The inner notifier drops these without calling the OA.

    If the wrapper reserved first it would spend a slot on a message that
    provably cannot be delivered — and there are only eight. Cheap to get
    right, invisible when wrong until a user runs out of replies early.
    """
    await open_window(window_store)
    client = FakeOAClient(window_store)

    result = await notifier_for(window_store, client).send_message(0, text)

    assert result is None
    assert client.sent == []
    assert window_store.rows[SENDER].free_msg_count == 0


@pytest.mark.asyncio
async def test_a_photo_with_neither_url_nor_caption_costs_no_slot(window_store):
    await open_window(window_store)
    client = FakeOAClient(window_store)

    result = await notifier_for(window_store, client).send_photo(0, b"png-bytes")

    assert result is None
    assert client.sent == []
    assert client.images == []
    assert window_store.rows[SENDER].free_msg_count == 0


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_photo_with_a_url_spends_exactly_one_slot(window_store):
    await open_window(window_store)
    client = FakeOAClient(window_store)

    result = await notifier_for(window_store, client).send_photo(
        0, b"png-bytes", caption="Net worth", image_url="https://cdn/x.png"
    )

    assert result == {"ok": True, "channel": "zalo"}
    assert client.images == [(SENDER, "https://cdn/x.png", "Net worth")]
    assert window_store.rows[SENDER].free_msg_count == 1


@pytest.mark.asyncio
async def test_a_caption_only_photo_is_still_one_cs_message(window_store):
    """No ``image_url`` → the inner notifier degrades to a text send.

    Zalo charges that as a consulting message like any other, so the
    ledger has to charge it too — and exactly once, not once for the
    photo and once for the fallback.
    """
    await open_window(window_store)
    client = FakeOAClient(window_store)

    result = await notifier_for(window_store, client).send_photo(
        0, b"png-bytes", caption="Tài sản ròng 1tr250"
    )

    assert result == {"ok": True, "channel": "zalo"}
    assert client.sent == [(SENDER, "Tài sản ròng 1tr250")]
    assert window_store.rows[SENDER].free_msg_count == 1


# ---------------------------------------------------------------------------
# Compensation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_transport_failure_hands_the_slot_back(window_store):
    """The client has already exhausted its own retries by this point.

    So the failure is real, the message did not land, and holding the
    slot would quietly shrink the allowance for a user who received
    nothing.
    """
    await open_window(window_store)
    client = FakeOAClient(window_store, ok=False)

    result = await notifier_for(window_store, client).send_message(0, "thử")

    assert result is None
    assert client.sent == [(SENDER, "thử")]
    assert window_store.rows[SENDER].free_msg_count == 0
    assert window_store.events.count("release") == 1


@pytest.mark.asyncio
async def test_an_exception_hands_the_slot_back_and_still_propagates(window_store):
    """The port says implementations don't raise, so this is a bug.

    Swallowing it would hide the bug; leaving the slot spent would skew
    the ledger. Do both: refund, then let the worker mark the row
    ``failed``.
    """
    await open_window(window_store)
    boom = RuntimeError("socket closed mid-write")
    client = FakeOAClient(window_store, error=boom)

    with pytest.raises(RuntimeError, match="socket closed"):
        await notifier_for(window_store, client).send_message(0, "thử")

    assert window_store.rows[SENDER].free_msg_count == 0
    assert window_store.events.count("release") == 1


@pytest.mark.asyncio
async def test_a_refund_cannot_land_in_a_window_opened_since(window_store):
    """A newer inbound message rotated the window mid-send.

    Refunding into the *new* window would hand the user a ninth message
    in it. ``release_send`` guards on window identity, so the refund is a
    no-op and the fresh allowance stays intact at eight.
    """
    await open_window(window_store)

    class RotatingClient(FakeOAClient):
        async def send_message(self, recipient_id, text):
            await svc.record_inbound(window_store, zalo_user_id=SENDER)
            return await super().send_message(recipient_id, text)

    client = RotatingClient(window_store, ok=False)

    result = await notifier_for(window_store, client).send_message(0, "thử")

    assert result is None
    assert window_store.rows[SENDER].free_msg_count == 0


@pytest.mark.asyncio
async def test_a_failed_refund_never_masks_the_delivery_failure(window_store, caplog):
    """Worst case the counter stays one high until the next inbound.

    That is strictly better than replacing a delivery failure with a
    stack trace from the compensation and losing the original reason.
    """
    await open_window(window_store)
    client = FakeOAClient(window_store, ok=False)
    notifier = WindowedZaloNotifier(
        ZaloNotifier(client=client, zalo_user_id=SENDER),
        SENDER,
        # Opens: 1 = the reservation, 2 = the refund.
        session_factory=session_factory_for(window_store, fail_on_open={2}),
    )

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = await notifier.send_message(0, "thử")

    assert result is None
    assert any("zalo.window.release_failed" in r.getMessage() for r in caplog.records)
    assert window_store.rows[SENDER].free_msg_count == 1


# ---------------------------------------------------------------------------
# Rejection — the half of the ledger that is *not* refunded (#4)
# ---------------------------------------------------------------------------
#
# The line release draws is "did the request reach Zalo?", not "did it
# succeed?". ``False`` means it demonstrably never left us and is safe to
# refund; ``ZaloSendRejected`` means Zalo answered no and may already have
# charged the attempt. These tests pin that asymmetry, because getting it
# backwards is how a user whose sends Zalo keeps rejecting loops forever
# against our own counter.


@pytest.mark.asyncio
async def test_a_rejected_send_keeps_the_slot_spent(window_store):
    await open_window(window_store)
    client = FakeOAClient(
        window_store, error=ZaloSendRejected("app error -32 after 3 retries")
    )

    result = await notifier_for(window_store, client).send_message(0, "thử")

    # Same answer to the caller as any other delivery failure — the
    # ``Notifier`` port owes them ``None``, not an exception.
    assert result is None
    assert window_store.rows[SENDER].free_msg_count == 1
    assert "release" not in window_store.events


@pytest.mark.asyncio
async def test_a_rejected_photo_keeps_its_slot_too(window_store):
    """Same rule on the image path — one CS message, one slot, and the
    OA charged for it either way."""
    await open_window(window_store)
    client = FakeOAClient(window_store, error=ZaloSendRejected("http 400"))

    result = await notifier_for(window_store, client).send_photo(
        0, b"", caption="biểu đồ", image_url="https://cdn.example/c.png"
    )

    assert result is None
    assert window_store.rows[SENDER].free_msg_count == 1
    assert "release" not in window_store.events


@pytest.mark.asyncio
async def test_a_rejection_is_logged_and_counted_without_the_sender_id(
    window_store, caplog
):
    """It reaches both sinks the runbook greps for: its own
    ``zalo.send.rejected`` warning, and the ordinary blocked line under
    ``send_failed`` so a rejection spike shows up in the same aggregate
    as every other kind of "nothing arrived"."""
    await open_window(window_store)
    client = FakeOAClient(window_store, error=ZaloSendRejected("http 400 boom"))

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await notifier_for(window_store, client).send_message(0, "thử")

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "zalo.send.rejected" in blob
    assert f"{mod.BLOCKED_LOG_RECORD} reason={svc.REASON_SEND_FAILED}" in blob
    assert SENDER not in blob
    # ``used`` is the count *after* the reservation: the slot is gone, and
    # the log has to say so or the runbook's arithmetic stops working.
    assert "used=1" in blob


@pytest.mark.asyncio
async def test_a_rejection_never_re_raises_into_the_caller(window_store):
    """A rejection is an ordinary delivery failure, not a bug — unlike
    the unexpected-exception path, which refunds *and* propagates."""
    await open_window(window_store)
    rejected = FakeOAClient(window_store, error=ZaloSendRejected("nope"))
    bug = FakeOAClient(window_store, error=RuntimeError("socket closed mid-write"))

    assert await notifier_for(window_store, rejected).send_message(0, "a") is None
    with pytest.raises(RuntimeError):
        await notifier_for(window_store, bug).send_message(0, "b")

    # One spent (the rejection), one reserved-then-refunded (the bug).
    assert window_store.rows[SENDER].free_msg_count == 1
    assert window_store.events.count("release") == 1


@pytest.mark.asyncio
async def test_repeated_rejections_exhaust_the_allowance_and_stop(window_store):
    """The ceiling this asymmetry exists to hold.

    Eight rejected sends spend the window; the ninth is refused before
    the transport is touched, so a failing OA can't be turned into an
    unbounded outbound loop.
    """
    await open_window(window_store)
    client = FakeOAClient(window_store, error=ZaloSendRejected("http 400"))
    notifier = notifier_for(window_store, client)

    for _ in range(FREE_MESSAGE_QUOTA + 1):
        assert await notifier.send_message(0, "thử") is None

    assert len(client.sent) == FREE_MESSAGE_QUOTA
    assert window_store.rows[SENDER].free_msg_count == FREE_MESSAGE_QUOTA


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_racing_sends_cannot_both_take_the_last_slot(window_store):
    """Five alerts fire at once with one slot left; one wins.

    Caveat worth stating plainly: ``FakeWindowStore`` does not model
    Postgres row locking, so this test proves the *wrapper* asks once per
    send and honours the answer. That the ``UPDATE ... WHERE
    free_msg_count < 8`` itself is atomic under two real connections is a
    Postgres property, asserted on the compiled SQL in
    ``test_zalo_window_service.py``. Both halves are needed; neither
    covers the other.
    """
    await open_window(window_store, used=FREE_MESSAGE_QUOTA - 1)
    client = FakeOAClient(window_store)
    notifier = notifier_for(window_store, client)

    results = await asyncio.gather(
        *(notifier.send_message(0, f"cảnh báo {i}") for i in range(5))
    )

    assert sum(r is not None for r in results) == 1
    assert len(client.sent) == 1
    assert window_store.rows[SENDER].free_msg_count == FREE_MESSAGE_QUOTA


# ---------------------------------------------------------------------------
# The factory, and the wiring that depends on it
# ---------------------------------------------------------------------------


def test_the_factory_returns_a_windowed_notifier():
    """Constructed with an explicit client, so no env is read here."""
    notifier = build_zalo_notifier(SENDER, client=FakeOAClient(None))

    assert isinstance(notifier, WindowedZaloNotifier)
    assert notifier.channel == "zalo"


def test_the_factory_falls_back_to_the_process_wide_client(monkeypatch):
    sentinel = FakeOAClient(None)
    monkeypatch.setattr(mod, "get_zalo_oa_client", lambda: sentinel)

    notifier = build_zalo_notifier(SENDER)

    assert notifier._inner._client is sentinel


def test_the_resolver_hands_out_window_aware_notifiers(monkeypatch):
    """The fan-out path is where a bypass would be most expensive.

    A proactive alert reaching a user whose window shut is exactly the
    send Zalo rejects, and #3.2's whole claim is that there is no way to
    construct a Zalo notifier that skips the ledger.
    """
    from types import SimpleNamespace

    from backend.ports import notifier as notifier_port
    from backend.services import notifier_resolver

    monkeypatch.setattr(
        notifier_resolver, "get_zalo_oa_client", lambda: FakeOAClient(None)
    )
    monkeypatch.setattr(notifier_port, "get_notifier", lambda: object())
    monkeypatch.setattr(notifier_resolver, "get_notifier", lambda: object())

    user = SimpleNamespace(id="u-1", telegram_id=12345, zalo_user_id=SENDER)
    targets = notifier_resolver.resolve_targets(user)

    zalo_target = next(t for t in targets if t.channel == "zalo")
    assert isinstance(zalo_target.notifier, WindowedZaloNotifier)
    assert zalo_target.target_id == SENDER


def test_the_resolver_drops_zalo_when_the_channel_flag_is_off(monkeypatch, caplog):
    """``ZALO_CHANNEL_ENABLED=false`` must be a real kill switch (#2/#6).

    Credentials deliberately outlive the flag so ``/admin/zalo-quota``
    still answers during a rollback — which means the credential can no
    longer be what gates fan-out. ``is_send_enabled`` is, and it is
    checked *before* ``is_configured`` so a rolled-back server stays
    silent on Zalo even with a perfectly good token in the table.
    """
    from types import SimpleNamespace

    from backend.services import notifier_resolver

    class DisabledClient(FakeOAClient):
        is_configured = True
        is_send_enabled = False

    monkeypatch.setattr(
        notifier_resolver, "get_zalo_oa_client", lambda: DisabledClient(None)
    )
    monkeypatch.setattr(notifier_resolver, "get_notifier", lambda: object())

    user = SimpleNamespace(id="u-1", telegram_id=12345, zalo_user_id=SENDER)
    with caplog.at_level(logging.WARNING, logger="backend.services.notifier_resolver"):
        targets = notifier_resolver.resolve_targets(user)

    # Telegram is untouched: a rollback must not cost the user their
    # alerts, only the channel that was rolled back.
    assert [t.channel for t in targets] == ["telegram"]
    # And it is not an error — a deliberate flag-off is not worth waking
    # anyone at 3am, unlike the missing-credential case below it.
    assert caplog.records == []


def test_no_production_module_builds_a_bare_zalo_notifier():
    """The factory is only load-bearing while nothing routes around it.

    A new caller writing ``ZaloNotifier(...)`` by hand would send without
    claiming a slot, and nothing else in the suite would fail. This is
    the tripwire. If a legitimate second transport-only use ever appears,
    add it here with the reason.
    """
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2] / "backend"
    offenders = [
        path.relative_to(backend).as_posix()
        for path in backend.rglob("*.py")
        if "ZaloNotifier(" in path.read_text(encoding="utf-8")
        and path.name not in {"zalo_notifier.py", "zalo_window_notifier.py"}
    ]

    assert offenders == []
