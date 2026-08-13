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
* the sender is already linked → let onboarding answer first if it is
  still running (#4.3), otherwise classify the message and dispatch it
  through the shared intent stack (#2.3);
* otherwise → the sender is new: mint the account and start onboarding
  right here (#4.3). The OA is a signup channel now, so "no link and no
  token" means *starting*, not *failing*.

From whitelist to blocklist (#4.1)
----------------------------------
5.0 shipped a seven-intent whitelist because the Zalo renderer could
only shape a handful of answers. 5.1 finished the renderer (#2.1–#2.4)
and the button mapper (#3.2–#3.3), so the whitelist had become the only
thing keeping Zalo behind Telegram. It is gone: every intent now goes
through the *same* dispatcher, and only two narrow classes are held
back.

**Wizard-launching intents** (``WIZARD_LAUNCHING_INTENTS``). These
handlers do not return an answer — they push a multi-step Telegram
keyboard themselves and return ``""``. Two independent reasons they
cannot run from here: Zalo has no such keyboard to push into, and since
#4.2 made ``telegram_id`` nullable, a Zalo-only account would have them
sending to ``chat_id=None``. That the set of intents Zalo cannot render
is *exactly* the set that self-sends to Telegram is not a coincidence —
both follow from "the handler owns its own UI" — so this reuses the
dispatcher's own table instead of restating it.

**Anything that would persist flow state**
(``persists_flow_state``). Below ``CONFIRM_THRESHOLD``, and on the
medium-confidence write path, the dispatcher stores state
(``set_awaiting_clarification`` / ``set_pending_action``) that only
``free_form_text`` knows how to consume. Arming it from Zalo would
ambush the user on their *next Telegram message* — a reply to a
question they were asked on another channel hours ago. So we ask again
here instead.

Both are decided on ``result`` **before** dispatch, and that ordering
is the point: the skipped path then costs no handler execution, no
second LLM call, and — crucially — can have no side effects. Each
class has its own ``fallback`` copy, phrased as an invitation rather
than a failure, and the intent is logged so the gap is visible.

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
from backend.bot.handlers import zalo_onboarding
from backend.intent.dispatcher import WIZARD_LAUNCHING_INTENTS, persists_flow_state
from backend.models.user import User
from backend.ports.notifier import get_notifier
from backend.services import zalo_catchup_service, zalo_linking_service
from backend.services.user_status import is_user_allowed
from backend.utils.zalo_copy import linking as linking_copy, text as zalo_text
from backend.utils.zalo_events import ZaloEvent

logger = logging.getLogger(__name__)

# Why Zalo could not serve a message. Kept as plain strings because
# they end up in two places that are not code — the log line an operator
# greps and the analytics property that tells us *which* gap is costing
# us answers. "wizard" and "flow_state" are the two blocklist classes
# from the module docstring; "error" is the classifier or a handler
# blowing up.
REASON_WIZARD = "wizard"
REASON_FLOW_STATE = "flow_state"
REASON_ERROR = "error"

# Reason → the ``fallback`` key we answer with. Three separate strings
# rather than one generic apology: "this needs Telegram" and "say that
# again please" ask the user for completely different next steps, and a
# message that names the wrong one is worse than no message.
_REASON_COPY = {
    REASON_WIZARD: "unsupported",
    REASON_FLOW_STATE: "unclear",
    REASON_ERROR: "body",
}

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

    if linked is None:
        # Phase 5.1 #4.3 — the OA is a signup channel now. A stranger who
        # isn't holding a token is starting, not failing: mint the account
        # and greet them instead of answering "mã không hợp lệ" to someone
        # who never typed a code.
        created = await zalo_onboarding.start_new_user(
            db, notifier=notifier, zalo_user_id=event.sender_id
        )
        return created.id if created is not None else None

    # Onboarding gets first refusal on the text; it returns False the
    # moment the user has finished, and dispatch proceeds as before.
    if await zalo_onboarding.handle_text(
        db, notifier=notifier, user=linked, text=event.text
    ):
        return linked.id

    # Phase 5.1 #4.5 — a Zalo-only user has no second channel to carry
    # what the proactive jobs skipped. Computed *before* dispatch, because
    # the silence is measured from their previous inbound row and dispatch
    # may write rows of its own; sent *after* the answer, so an urgent
    # question is never made to wait behind three days of news.
    catchup = await _catchup_line(db, user=linked, msg_id=event.msg_id)

    await _dispatch_intent(db, notifier=notifier, user=linked, text=event.text)

    if catchup:
        await _send_catchup(notifier, user=linked, line=catchup)
    return linked.id


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


async def _catchup_line(db: AsyncSession, *, user: User, msg_id: str) -> str | None:
    """Ask #4.5 what this user missed, and never let the answer cost them.

    Catch-up is a courtesy on top of the reply the user actually asked
    for. It runs *before* dispatch, so an exception here would sink the
    whole handler and the user would get nothing at all — which is a far
    worse trade than losing one line of news. Swallowed and logged.
    """
    try:
        return await zalo_catchup_service.build_catchup_line(
            db, user=user, exclude_msg_id=msg_id
        )
    except Exception:
        logger.exception("zalo.catchup build failed — answering without it")
        return None


async def _send_catchup(
    notifier: WindowedZaloNotifier, *, user: User, line: str
) -> None:
    """Send the catch-up as its own bubble, after the answer.

    Its own message rather than a prefix on the reply: the reply is
    already sized for one Zalo bubble, and prepending to it would push
    the part the user asked for off the bottom. It does spend a second
    slot of the 8-per-window quota, which is the honest cost of the
    channel being the only one this user has.

    ``send_message`` returning ``None`` means the window closed between
    the reply and this line. That is a drop, not an error — the news is
    still uncelebrated, so the next time they write it is still waiting.
    """
    sent = await notifier.send_message(0, line)
    analytics.track(
        "zalo_catchup",
        user_id=user.id,
        properties={"channel": CHANNEL_ZALO, "delivered": sent is not None},
    )


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


def _unserved_reason(result) -> str | None:
    """Why Zalo cannot serve ``result``, or ``None`` to dispatch it.

    Both checks read the dispatcher's own tables rather than a local
    copy, so a seventh wizard intent or a change to the confidence
    policy lands here without an edit — which is the whole reason #4.1
    made them public.

    Wizard is tested first even though a low-confidence wizard intent
    satisfies both: "open Bé Tiền on Telegram" is something the user can
    act on, while "say that again" would send them round a loop that
    ends at the same wall.
    """
    if result.intent in WIZARD_LAUNCHING_INTENTS:
        return REASON_WIZARD
    if persists_flow_state(result):
        return REASON_FLOW_STATE
    return None


async def _dispatch_intent(
    db: AsyncSession,
    *,
    notifier: WindowedZaloNotifier,
    user: User,
    text: str,
) -> None:
    """Classify a linked user's message and answer it on Zalo.

    Sends at most one message. Three outcomes:

    * served → dispatch, send the outcome text;
    * served but the handler already replied itself (empty outcome
      text — ``action_quick_transaction`` sends its own confirmation,
      which #2.4 made channel-aware) → send nothing more, or the user
      gets the same transaction twice;
    * unserved — a wizard intent, something that would persist flow
      state, or an error → the matching ``fallback`` copy, phrased as an
      invitation rather than a failure.

    The reason is decided from ``result`` *before* dispatch, so an
    unserved message costs no handler execution and can leave no trace
    on the user's data.

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
    reason = REASON_ERROR
    try:
        result = await get_pipeline().classify(text)
        reason = _unserved_reason(result)
        if reason is None:
            outcome = await get_dispatcher().dispatch(result, user, db)
    except Exception:
        # Never log ``text`` — it is the user's own message. Note this
        # resets ``reason`` to ``error`` even when the classifier had
        # already cleared the message: a handler that raised is an
        # error, not an unsupported intent.
        reason = REASON_ERROR
        logger.exception("zalo.inbound intent dispatch failed; sending fallback")

    latency_ms = int((time.perf_counter() - started) * 1000)
    intent_name = result.intent.value if result is not None else "error"
    logger.info(
        "zalo.inbound intent=%s confidence=%s reason=%s kind=%s latency_ms=%d",
        intent_name,
        round(result.confidence, 2) if result is not None else "-",
        reason or "-",
        outcome.kind if outcome is not None else "-",
        latency_ms,
    )
    # Same event name as the Telegram path so the funnel stays one
    # series; ``channel`` is what splits it. No message text — the
    # intent label and the confidence are the whole payload. ``reason``
    # is null on the happy path precisely so "how often does Zalo fail
    # to answer, and why" is one group-by rather than a subtraction.
    analytics.track(
        EVENT_INTENT_CLASSIFIED,
        user_id=user.id,
        properties={
            "channel": CHANNEL_ZALO,
            "intent": intent_name,
            "confidence": round(result.confidence, 3) if result is not None else 0.0,
            "classifier": result.classifier_used if result is not None else "none",
            "served": reason is None,
            "unserved_reason": reason,
            "latency_ms": latency_ms,
        },
    )

    if outcome is None:
        # ``reason`` is never None here: it is None only when dispatch
        # ran, and dispatch either returns an outcome or raises — and
        # the ``except`` puts ``error`` back.
        await notifier.send_message(
            0, zalo_text("fallback", _REASON_COPY[reason or REASON_ERROR])
        )
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
