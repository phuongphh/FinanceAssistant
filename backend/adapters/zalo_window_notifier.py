"""Quota-enforcing wrapper around :class:`ZaloNotifier` (Phase 5.0 #3.2).

The DoD this file implements: *"Ngoài cửa sổ 48h hoặc đã dùng 8 tin →
không gọi ``/message/cs``, Telegram vẫn nhận, log rõ lý do."*

Where the enforcement lives, and why here
-----------------------------------------
Every outbound Zalo message goes through a :class:`Notifier`, so the
notifier is the only seam that *all* of them share — the inbound reply,
the linking confirmation, the transaction card, the cashflow alert. Put
the ceiling anywhere upstream and each new caller has to remember to ask
first; put it here and forgetting is not an option, because there is no
other way to reach the OA.

The alternative — deciding in :func:`resolve_targets`, where the channel
list is built — was rejected twice over. It would be a check separated
from the send by an ``await`` (a race the phase doc is explicit about:
``can_send()`` is observability, never a gate), and it would make target
resolution async for the benefit of one channel out of two.

Why this is an adapter and not a service
----------------------------------------
The reservation is only load-bearing once **committed** — an
uncommitted one holds a row lock and is invisible to every other worker,
which is precisely the over-send it exists to stop. Services are
flush-only by contract, so the commit has to happen at an edge, and
transport is exactly the edge this is. (``test_service_boundary.py``
scans ``backend/services/``; landing the commit here keeps the rule
intact rather than buying a third allowlist entry.)

The session is our own, opened per send, never the caller's. Riding the
caller's session would hold the window row locked for the whole handler
— including the LLM call — and serialise every other send to the same
user behind it.

Ordering, and which way it errs
-------------------------------
reserve → commit → send → (release + commit only if the transport
failed). A crash between the reservation and the send spends a slot on
a message nobody received; the reverse ordering would let eight
concurrent sends all read 7 and all deliver. *Thà đếm dư 1 khi crash
giữa chừng còn hơn vượt trần thật.*

Release is deliberately narrow, and the line it draws is *"did the
request reach Zalo?"* — not *"did it succeed?"*. ``ZaloOAClient``
answers ``False`` only when the send demonstrably never left us (no
usable token, empty arguments, connection refused); those are safe to
refund, because Zalo cannot have counted a message it never saw. When
Zalo answered and answered no — an app error, a non-retryable HTTP
status, a rate-limit that outlasted the retry budget, or a transport
failure mid-flight whose outcome we cannot know — the client raises
:class:`~backend.adapters.zalo_oa.ZaloSendRejected` and we keep the
slot spent. Refunding those would let a user whose sends Zalo is
rejecting for quota reasons loop forever against our own counter,
which is exactly the ceiling this file exists to hold.

:func:`release_send` additionally guards on window identity, so even a
sanctioned refund can never land in a window a newer inbound message
has since opened.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from backend import analytics
from backend.adapters.zalo_notifier import (
    ZaloNotifier,
    strip_markdown,
    truncate_for_zalo,
)
from backend.adapters.zalo_oa import (
    ZaloOAClient,
    ZaloSendRejected,
    get_zalo_oa_client,
)
from backend.database import get_session_factory
from backend.services import zalo_window_service

logger = logging.getLogger(__name__)

__all__ = [
    "BLOCKED_LOG_RECORD",
    "BLOCK_REASONS",
    "REASON_NOT_CONFIGURED",
    "REASON_SEND_FAILED",
    "WindowedZaloNotifier",
    "build_zalo_notifier",
]

# What was being sent, for the block log. Not the message text — that is
# the user's own content and never reaches a log line.
KIND_TEXT = "text"
KIND_PHOTO = "photo"

# The two reasons this adapter is the one to discover: no usable
# credential on this server, and a transport that refused after its own
# retries. Re-exported rather than declared — the closed vocabulary lives
# in the window service so the metrics service can group on it without
# importing an adapter (see that module for the reasoning). These aliases
# exist so call sites here read as local names.
REASON_NOT_CONFIGURED = zalo_window_service.REASON_NOT_CONFIGURED
REASON_SEND_FAILED = zalo_window_service.REASON_SEND_FAILED
BLOCK_REASONS = zalo_window_service.BLOCK_REASONS

# The canonical name of the "a message did not go out" log record (#3.3).
# The runbook greps this exact string, so it is a published interface,
# not a formatting choice.
BLOCKED_LOG_RECORD = "zalo.send.blocked"


class WindowedZaloNotifier:
    """A :class:`Notifier` that claims a free-message slot before sending.

    Delegates everything about *rendering* to the wrapped
    :class:`ZaloNotifier` — stripping, truncation, the OA call — and adds
    exactly one thing: the send doesn't happen unless the 48h window is
    open and the eight-message allowance has room.

    Blocked sends return ``None``, the same value the inner notifier
    returns for a failed one. Callers already treat that as "this channel
    didn't take it" and fall through to Telegram, which is the behaviour
    the DoD asks for.
    """

    channel = "zalo"

    def __init__(
        self,
        inner: ZaloNotifier,
        zalo_user_id: str,
        *,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._inner = inner
        self._zalo_user_id = zalo_user_id
        # Injected in tests; resolved lazily in production so importing
        # this module never touches the engine.
        self._session_factory = session_factory

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None:
        """Reserve a slot, then hand the message to the inner notifier.

        The body is stripped here as well as inside — ``strip_markdown``
        is idempotent and ``truncate_for_zalo`` is a no-op on text that
        already fits, so the duplication is free and it buys the one
        thing that matters: a message that renders to nothing (all
        markup, or empty to begin with) never reaches the OA, so it must
        never cost a slot either.
        """
        body = truncate_for_zalo(strip_markdown(text))
        if not body:
            return None

        return await self._guarded(
            lambda: self._inner.send_message(
                chat_id,
                body,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                **kwargs,
            ),
            kind=KIND_TEXT,
        )

    async def send_photo(
        self,
        chat_id: int,
        photo: bytes,
        *,
        caption: str = "",
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None:
        """Same discipline for images.

        Without an ``image_url`` the inner notifier degrades to a
        caption-only text send — still one CS message, still one slot.
        With neither a URL nor a caption it sends nothing, so neither do
        we reserve.
        """
        if not kwargs.get("image_url") and not strip_markdown(caption):
            return None

        return await self._guarded(
            lambda: self._inner.send_photo(
                chat_id,
                photo,
                caption=caption,
                reply_markup=reply_markup,
                **kwargs,
            ),
            kind=KIND_PHOTO,
        )

    # -- internals ---------------------------------------------------------

    async def _guarded(
        self,
        send: Callable[[], Awaitable[dict | None]],
        *,
        kind: str,
    ) -> dict | None:
        if not self._inner.is_configured:
            # Checked before the reservation, not after: a server with no
            # OA credential would otherwise spend a slot on every send and
            # pay two DB round-trips to do it. ``is_configured`` is
            # optimistic (it can be true and the token still turn out
            # unusable) — that case lands on ``send_failed`` below, which
            # is the honest label for it.
            self._blocked(REASON_NOT_CONFIGURED, kind=kind, used=0, remaining=0)
            return None

        reservation = await self._reserve()
        if not reservation.granted:
            # The line the DoD asks for. Reason is one of the service's
            # stable strings, used verbatim as the counter label rather
            # than re-derived from prose.
            self._blocked(
                reservation.reason,
                kind=kind,
                used=reservation.free_msg_count,
                remaining=reservation.remaining,
            )
            return None

        try:
            result = await send()
        except ZaloSendRejected as exc:
            # Zalo answered, and answered no. It may already have charged
            # the OA for the attempt, so the slot stays spent — the whole
            # point of the exception is that it is *not* the fail-open
            # ``False`` case below. Not re-raised: this is an ordinary
            # delivery failure, not a bug, and the ``Notifier`` port owes
            # its callers ``None`` for that.
            logger.warning(
                "zalo.send.rejected kind=%s zalo_user=%s used=%d remaining=%d: %s",
                kind,
                zalo_window_service.mask_zalo_id(self._zalo_user_id),
                reservation.free_msg_count,
                reservation.remaining,
                exc,
            )
            self._blocked(
                REASON_SEND_FAILED,
                kind=kind,
                used=reservation.free_msg_count,
                remaining=reservation.remaining,
            )
            return None
        except Exception:
            # The port says implementations don't raise, so this is a bug
            # rather than a delivery failure — but the ledger still has to
            # come out right, and swallowing it would hide the bug. Give
            # the slot back, then let it propagate to the worker, which
            # marks the row ``failed``.
            await self._release(reservation)
            self._blocked(
                REASON_SEND_FAILED,
                kind=kind,
                used=reservation.free_msg_count,
                remaining=reservation.remaining,
            )
            raise

        if result is None:
            await self._release(reservation)
            # Counted as a block too: from the user's side "nothing
            # arrived" is one symptom, and splitting transport failures
            # into a series the runbook never mentions is how a silent
            # outage gets missed. The ``reason`` is what tells the two
            # apart.
            self._blocked(
                REASON_SEND_FAILED,
                kind=kind,
                used=reservation.free_msg_count,
                remaining=reservation.remaining,
            )
            return None

        logger.debug(
            "zalo.send.delivered kind=%s zalo_user=%s used=%d remaining=%d",
            kind,
            zalo_window_service.mask_zalo_id(self._zalo_user_id),
            reservation.free_msg_count,
            reservation.remaining,
        )
        analytics.track(
            analytics.EventType.ZALO_SEND_DELIVERED,
            properties={
                "channel": self.channel,
                "kind": kind,
                "used": reservation.free_msg_count,
                "remaining": reservation.remaining,
            },
        )
        return result

    def _blocked(self, reason: str, *, kind: str, used: int, remaining: int) -> None:
        """Record one message that did not go out.

        Two sinks, on purpose. The log line carries the masked sender so
        an operator can follow a single conversation; the analytics event
        carries no identifier at all, because it is only ever read in
        aggregate and an events table that accumulates recipient ids is a
        PII liability nobody asked for.

        ``track`` is fire-and-forget (it schedules a task and swallows
        every failure), so this adds nothing measurable to the reply path
        and cannot turn a metrics outage into a delivery outage.
        """
        logger.info(
            "%s reason=%s kind=%s zalo_user=%s used=%d remaining=%d",
            BLOCKED_LOG_RECORD,
            reason,
            kind,
            zalo_window_service.mask_zalo_id(self._zalo_user_id),
            used,
            remaining,
        )
        analytics.track(
            analytics.EventType.ZALO_SEND_BLOCKED,
            properties={
                "channel": self.channel,
                "reason": reason,
                "kind": kind,
                "used": used,
                "remaining": remaining,
            },
        )

    async def _reserve(self) -> zalo_window_service.Reservation:
        """Claim a slot in its own committed transaction.

        Committed *before* returning, on purpose: see the module
        docstring. Two racing sends therefore meet on the row lock inside
        Postgres rather than both reading a stale count.
        """
        factory = self._session_factory or get_session_factory()
        async with factory() as db:
            reservation = await zalo_window_service.reserve_send(
                db, zalo_user_id=self._zalo_user_id
            )
            await db.commit()
        return reservation

    async def _release(self, reservation: zalo_window_service.Reservation) -> None:
        """Hand back a slot whose send didn't happen. Never raises.

        We are already on a failure path; a compensation that blows up
        would replace a delivery failure with a stack trace and lose the
        original reason. Worst case the counter stays one high until the
        next inbound message resets it.
        """
        factory = self._session_factory or get_session_factory()
        try:
            async with factory() as db:
                await zalo_window_service.release_send(
                    db,
                    zalo_user_id=self._zalo_user_id,
                    window_expires_at=reservation.window_expires_at,
                )
                await db.commit()
        except Exception:
            logger.exception(
                "zalo.window.release_failed zalo_user=%s — slot stays spent",
                zalo_window_service.mask_zalo_id(self._zalo_user_id),
            )


def build_zalo_notifier(
    zalo_user_id: str,
    *,
    client: ZaloOAClient | None = None,
    session_factory: Callable[[], Any] | None = None,
) -> WindowedZaloNotifier:
    """The only sanctioned way to construct a Zalo notifier.

    Constructing :class:`ZaloNotifier` directly still works — it is the
    transport, and the window wrapper needs it — but doing so from a
    handler or a service silently bypasses the quota. Every such site was
    routed through here in #3.2; a new one should be too.

    Does not check ``client.is_configured``. Callers that can fall back
    to another channel check it themselves and log their own reason (see
    :func:`backend.services.notifier_resolver.resolve_targets`); making
    this return ``None`` would push an ``if`` onto callers that have no
    fallback anyway.
    """
    oa_client = client or get_zalo_oa_client()
    return WindowedZaloNotifier(
        ZaloNotifier(client=oa_client, zalo_user_id=zalo_user_id),
        zalo_user_id,
        session_factory=session_factory,
    )
