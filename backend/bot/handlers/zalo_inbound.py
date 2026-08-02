"""Inbound Zalo OA message handler (Phase 5.0 #2.2).

Runs inside :mod:`backend.workers.zalo_worker`, never in the request
path — by the time this executes the webhook has already answered 200,
so latency here is invisible to Zalo and a slow LLM call cannot trigger
a redelivery.

What it decides
--------------
Exactly one branch per inbound message:

* the text carries a ``BT-XXXXXX`` code → redeem it and confirm on both
  channels (Phase 4B behaviour, moved here unchanged);
* the sender is already linked → classify the message and dispatch it
  through the shared intent stack (#2.3);
* otherwise → the linking nudge.

Why the thin slice is a whitelist (#2.3)
---------------------------------------
Zalo in 5.0 answers three things: capture a transaction, read a short
report, say hello. Everything else gets the ``fallback`` copy — an
invitation to Telegram, not an error.

The whitelist is checked on ``result.intent`` **before** dispatch, not
on the outcome afterwards, and that ordering is the point: an
out-of-slice intent then costs no handler execution, no second LLM
call, and — crucially — can have no side effects. Zalo is a reactive
channel where the user is sitting there waiting, so work we are going
to throw away should never start.

The whitelist also keeps a subtler invariant. Below
``CONFIRM_THRESHOLD`` the dispatcher persists Telegram flow state
(``set_awaiting_clarification`` / ``set_pending_action``) which only
``free_form_text`` knows how to consume; a Zalo message that armed it
would ambush the user on their *next Telegram message*. So low
confidence short-circuits to the fallback copy before dispatch, and
every intent left in the whitelist is one the dispatcher executes
outright at ≥ 0.5 — no confirm branch, no clarify branch, no
cross-channel state.

Layer contract: this handler routes and formats. It owns no
transaction (the worker commits once at the boundary), issues no raw
queries (``zalo_linking_service`` answers "who is this sender?"), and
reaches Telegram only through the :class:`Notifier` port.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.adapters.zalo_notifier import strip_markdown, unwrap_button_spans
from backend.adapters.zalo_window_notifier import (
    WindowedZaloNotifier,
    build_zalo_notifier,
)
from backend.bot.channel_context import CHANNEL_ZALO
from backend.intent.dispatcher import CONFIRM_THRESHOLD
from backend.intent.intents import IntentType
from backend.models.user import User
from backend.ports.notifier import get_notifier
from backend.services import zalo_linking_service
from backend.services.user_status import is_user_allowed
from backend.utils.zalo_copy import linking as linking_copy, text as zalo_text
from backend.utils.zalo_events import ZaloEvent

logger = logging.getLogger(__name__)

# The 5.0 thin slice. Deliberately small: every member here is an
# intent the dispatcher *executes* at medium confidence, so none of
# them can arm the Telegram confirm/clarify state machine (see module
# docstring). Widening this set means re-checking that property.
ZALO_SUPPORTED_INTENTS = frozenset(
    {
        IntentType.ACTION_QUICK_TRANSACTION,
        IntentType.QUERY_EXPENSES,
        IntentType.QUERY_EXPENSES_BY_CATEGORY,
        IntentType.QUERY_NET_WORTH,
        IntentType.QUERY_ASSETS,
        IntentType.GREETING,
        IntentType.HELP,
    }
)

# Redemption outcomes that mean the binding now exists.
_LINKED_STATUSES = frozenset({"linked", "user_relinked"})

# Redemption status → the copy key we answer with. Anything not listed
# (including "invalid" and any status a later change introduces) falls
# back to ``token_invalid``: a user who pasted a bad code needs the same
# nudge whatever the internal reason was.
_STATUS_COPY = {
    "already_used": "token_already_used",
    "expired": "token_expired",
}


async def handle_inbound_event(db: AsyncSession, *, event: ZaloEvent) -> UUID | None:
    """Process one inbound Zalo event.

    Returns the ``users.id`` this event belongs to, or ``None`` when the
    sender isn't linked to anyone — the worker stamps it on the
    ``zalo_updates`` row so an operator can trace a conversation without
    joining on the Zalo id.

    Never raises for ordinary "we can't help with this" cases; a genuine
    fault propagates so the worker records the row as ``failed``.
    """
    if not event.is_text:
        # The router filters these out already; belt-and-braces for the
        # orphan-recovery path, which replays whatever is on the row.
        logger.debug("zalo.inbound non-text event ignored: %s", event.event_name)
        return None

    if not event.sender_id or not event.text.strip():
        # An empty body (sticker, attachment-only) has nothing to act on.
        # Silence beats an error message the user didn't ask for.
        return None

    # Built here, once, and passed down: every reply this handler can
    # make goes through the same window-aware notifier, so the 48h /
    # 8-message ceiling applies to the linking confirmation and the
    # intent answer alike. Constructing ``ZaloNotifier`` directly would
    # send without claiming a slot.
    notifier = build_zalo_notifier(event.sender_id)
    linked = await zalo_linking_service.get_linked_user(db, event.sender_id)

    # A suspended account is suspended on every channel. Telegram rejects
    # at its worker (``_reject_if_suspended``); without the same gate here
    # Zalo would be the way around it — the sender could keep recording
    # transactions and reading balances on an account an admin has closed.
    # Checked before the token branch too, so a suspended user cannot
    # re-link their way past it either.
    if linked is not None and not await is_user_allowed(db, linked.id):
        return await _reject_suspended(notifier, user_id=linked.id)

    token = zalo_linking_service.normalize_token_input(event.text)
    if token:
        return await _redeem(
            db,
            notifier=notifier,
            token=token,
            zalo_user_id=event.sender_id,
            fallback_user_id=linked.id if linked else None,
        )

    if linked is not None:
        await _dispatch_intent(db, notifier=notifier, user=linked, text=event.text)
        return linked.id

    await notifier.send_message(0, linking_copy("token_invalid"))
    return None


async def _reject_suspended(
    notifier: WindowedZaloNotifier, *, user_id: UUID | None
) -> UUID | None:
    """Answer a suspended account and stop.

    Returns the user id anyway so the ``zalo_updates`` row still records
    who sent the message — a suspended user's traffic is exactly what an
    operator wants to be able to trace.

    Never logs the sender id, and never says *why* the account was
    suspended: this handler doesn't know, and guessing in the bubble
    would be worse than the contact address.
    """
    logger.info("zalo.inbound rejected: account suspended")
    await notifier.send_message(0, zalo_text("account", "suspended"))
    return user_id


def _plain_body(text: str) -> str:
    """Flatten a dispatcher outcome into text a Zalo bubble can carry.

    The markup rules themselves live in
    :mod:`backend.adapters.zalo_notifier` — one implementation, shared
    with :class:`~backend.adapters.zalo_content_renderer.ZaloContentRenderer`.
    The **order** is the part that matters here: ``strip_markdown`` first,
    so ``[đây](https://x.vn)`` collapses to ``đây``; unwrapping the
    brackets first would leave the URL stranded as ``đây(https://x.vn)``.

    What is local to this seam is the whitespace policy. Intent answers
    are short and are read in a single glance, and two adjacent buttons
    leave a gap that looks like a rendering fault, so runs collapse and
    blank lines go. A briefing keeps its paragraph breaks instead — same
    rule, different shape of message.
    """
    unwrapped = unwrap_button_spans(strip_markdown(text))
    lines = [" ".join(line.split()) for line in unwrapped.splitlines()]
    return "\n".join(line for line in lines if line)


async def _dispatch_intent(
    db: AsyncSession,
    *,
    notifier: WindowedZaloNotifier,
    user: User,
    text: str,
) -> None:
    """Classify a linked user's message and answer it on Zalo.

    Sends at most one message. Three outcomes:

    * in-slice and confident → dispatch, send the outcome text;
    * in-slice but the handler already replied itself (empty outcome
      text — ``action_quick_transaction`` sends its own confirmation,
      which #2.4 made channel-aware) → send nothing more, or the user
      gets the same transaction twice;
    * out of slice, low confidence, or a handler error → the fallback
      copy, which is phrased as an invitation rather than a failure.

    Errors are contained here rather than raised: a classifier timeout
    or a handler bug must not mark the ``zalo_updates`` row ``failed``
    and leave the user staring at silence — orphan recovery would then
    replay the message and could double-record the transaction.
    """
    started = time.perf_counter()
    # Imported lazily: this pulls in the whole intent stack (rule
    # patterns, LLM classifier, every handler) plus ``telegram_service``.
    # The webhook path imports this module to route link tokens, and a
    # server with the flag on but no linked users should not pay for the
    # intent stack at startup.
    from backend.bot.handlers.free_form_text import (
        EVENT_INTENT_CLASSIFIED,
        get_dispatcher,
        get_pipeline,
    )

    result = None
    outcome = None
    in_slice = False
    try:
        result = await get_pipeline().classify(text)
        in_slice = (
            result.intent in ZALO_SUPPORTED_INTENTS
            and result.confidence >= CONFIRM_THRESHOLD
        )
        if in_slice:
            outcome = await get_dispatcher().dispatch(result, user, db)
    except Exception:
        # Never log ``text`` — it is the user's own message.
        logger.exception("zalo.inbound intent dispatch failed; sending fallback")

    latency_ms = int((time.perf_counter() - started) * 1000)
    intent_name = result.intent.value if result is not None else "error"
    logger.info(
        "zalo.inbound intent=%s confidence=%s in_slice=%s kind=%s latency_ms=%d",
        intent_name,
        round(result.confidence, 2) if result is not None else "-",
        in_slice,
        outcome.kind if outcome is not None else "-",
        latency_ms,
    )
    # Same event name as the Telegram path so the funnel stays one
    # series; ``channel`` is what splits it. No message text — the
    # intent label and the confidence are the whole payload.
    analytics.track(
        EVENT_INTENT_CLASSIFIED,
        user_id=user.id,
        properties={
            "channel": CHANNEL_ZALO,
            "intent": intent_name,
            "confidence": round(result.confidence, 3) if result is not None else 0.0,
            "classifier": result.classifier_used if result is not None else "none",
            "in_slice": in_slice,
            "latency_ms": latency_ms,
        },
    )

    if outcome is None:
        await notifier.send_message(0, zalo_text("fallback", "body"))
        return

    body = _plain_body(outcome.text or "")
    if not body:
        # The handler self-sent (see docstring). Silence is the correct
        # answer, not a bug.
        return

    # Length stays the notifier's job — it truncates to the Zalo display
    # limit. The markup strip above is idempotent, so the notifier
    # repeating it costs a few regex passes and changes nothing.
    await notifier.send_message(0, body)


async def _redeem(
    db: AsyncSession,
    *,
    notifier: WindowedZaloNotifier,
    token: str,
    zalo_user_id: str,
    fallback_user_id: UUID | None,
) -> UUID | None:
    """Redeem a pasted ``BT-XXXXXX`` code and answer on both channels."""
    result = await zalo_linking_service.redeem_link_token(
        db, token=token, zalo_user_id=zalo_user_id
    )
    # Status only — the token and the sender id are both credentials of
    # a sort and must never reach the log.
    logger.info("zalo.inbound link_redemption status=%s", result.status)

    if result.status in _LINKED_STATUSES:
        # The binding is left in place — it costs nothing and means the
        # user is already linked when an admin lifts the suspension. What
        # we withhold is the cheery confirmation on both channels, which
        # would promise a channel that is about to refuse every message.
        if result.user_id is not None and not await is_user_allowed(db, result.user_id):
            return await _reject_suspended(notifier, user_id=result.user_id)
        await notifier.send_message(0, linking_copy("confirm_zalo"))
        await _confirm_on_telegram(db, user_id=result.user_id)
        return result.user_id

    await notifier.send_message(
        0, linking_copy(_STATUS_COPY.get(result.status, "token_invalid"))
    )
    return fallback_user_id


async def _confirm_on_telegram(db: AsyncSession, *, user_id: UUID | None) -> None:
    """Tell the Telegram side the pairing succeeded.

    Cross-channel by design: the code was issued in Telegram, so the
    confirmation closes the loop where the user started it. Goes through
    the :class:`Notifier` port rather than ``telegram_service`` so the
    handler stays swappable in tests and the layer contract holds.
    """
    if user_id is None:
        return
    user: User | None = await zalo_linking_service.get_user_by_id(db, user_id)
    if user is None or not user.telegram_id:
        # Zalo-only accounts have no Telegram side to confirm on. Not an
        # error — the Zalo confirmation already went out.
        return
    await get_notifier().send_message(
        user.telegram_id, linking_copy("confirm_telegram")
    )
