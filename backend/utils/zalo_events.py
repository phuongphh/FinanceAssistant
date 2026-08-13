"""Parse and identify one inbound Zalo OA event (Phase 5.0 #2.1).

The single place that knows the shape of a Zalo webhook body. The router,
the worker and the inbound handler all read events through
:func:`parse_event` so "where does the sender id live?" has exactly one
answer, and so a payload-shape surprise on staging is a one-line fix.

Why identity needs its own module
---------------------------------
Zalo re-delivers any event we don't answer with a 2xx
(``docs/conventions/zalo-operations.md`` §Webhook). Without a dedup key
one "ăn trưa 50k" becomes two recorded expenses. The key is normally
``message.msg_id``, but that row is still ``ASSUMED`` in the facts table —
some event types may carry no message id at all. So when it is absent we
derive a stable surrogate::

    sha256(app_id|sender_id|timestamp|text)

A *retry* of one delivery repeats all four components and therefore
collides, which is what we want. Two genuinely separate messages differ in
``timestamp`` (epoch **milliseconds**), so a user typing the same thing
twice is still captured twice — the failure mode that silently eats a
user's second coffee is worse than the one that costs a hash.

Everything here is pure: no DB, no settings, no I/O. ``app_id`` is passed
in by the caller (the router reads env, this module never does).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

# Events that represent a human typing at us. Anything else (follow,
# unfollow, delivery receipts) is acknowledged and dropped without a
# ``zalo_updates`` row: nothing is processed, so nothing can be processed
# twice, and the dedup table stays proportional to real conversation.
TEXT_EVENTS: frozenset[str] = frozenset({"user_send_text", "user_send_message"})

# Marks a key we derived rather than one Zalo gave us. Two reasons: an
# operator reading ``zalo_updates`` can tell instantly which path a row
# took, and a real msg_id can never collide with a surrogate even if Zalo
# starts issuing bare hex digests.
DERIVED_PREFIX = "d:"

# ``zalo_updates.msg_id`` is ``String(128)``. A longer id would raise on
# INSERT, the webhook would 500, and Zalo would retry it forever — so an
# oversized id is folded into a surrogate instead.
MAX_KEY_LENGTH = 128


@dataclass(frozen=True)
class ZaloEvent:
    """One inbound event, normalised.

    ``msg_id`` is the dedup key and is never empty for an event
    :func:`parse_event` returns — an event we cannot identify is an event
    we cannot safely process twice, so it is rejected rather than guessed
    at.
    """

    msg_id: str
    event_name: str
    sender_id: str
    text: str
    timestamp: str
    # True when ``msg_id`` is the derived surrogate rather than Zalo's own.
    # Worth logging during the soak: a channel running entirely on derived
    # keys means the ``message.msg_id`` facts row is wrong.
    derived_key: bool
    payload: dict[str, Any]

    @property
    def is_text(self) -> bool:
        """Whether this is inbound user text we act on."""
        return self.event_name in TEXT_EVENTS


def _as_text(value: Any) -> str:
    """Coerce a JSON scalar to text without inventing content.

    Zalo sends ``timestamp`` as a string of epoch milliseconds but some
    payloads carry it as a number; ``str()`` round-trips an int exactly.
    Containers (dict/list) are treated as absent — they are never valid
    values for the fields we read, and stringifying one would make the
    surrogate depend on Python's repr ordering.
    """
    if value is None or isinstance(value, (dict, list)):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        # A bool is an int in Python; none of these fields are ever
        # boolean, so treat it as absent rather than "True".
        return ""
    return str(value)


def derive_msg_id(
    *, app_id: str, sender_id: str, timestamp: str, text: str
) -> str:
    """Stable surrogate dedup key for an event with no ``msg_id``.

    ``|`` separates the components so that ("a", "bc") and ("ab", "c")
    hash differently — without a separator, shifting a character between
    adjacent fields would produce the same digest.
    """
    material = f"{app_id}|{sender_id}|{timestamp}|{text}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{DERIVED_PREFIX}{digest}"


def parse_event(payload: Any, *, app_id: str) -> ZaloEvent | None:
    """Normalise one webhook body, or return ``None`` if it is unusable.

    ``None`` means "acknowledge with 200 and do nothing": either the body
    isn't a Zalo event object, or it carries no identity we could dedup
    on. Both are cases where processing is unsafe and retrying would not
    help, so the caller must not enqueue anything.
    """
    if not isinstance(payload, Mapping):
        return None

    event_name = _as_text(payload.get("event_name"))
    sender = payload.get("sender")
    sender_id = _as_text(sender.get("id")) if isinstance(sender, Mapping) else ""
    message = payload.get("message")
    message = message if isinstance(message, Mapping) else {}
    text = _as_text(message.get("text"))
    timestamp = _as_text(payload.get("timestamp"))

    raw_msg_id = _as_text(message.get("msg_id"))
    derived_key = False
    if raw_msg_id and len(raw_msg_id) <= MAX_KEY_LENGTH:
        msg_id = raw_msg_id
    else:
        # A surrogate built from nothing identifies nothing: every such
        # body would collapse onto one key and the first one seen would
        # suppress every later one forever.
        if not sender_id or not timestamp:
            return None
        # No id, or one too long for the column. Both need a surrogate;
        # for the overlong case the id itself is the strongest available
        # identity, so it goes into the material.
        derived_key = True
        msg_id = derive_msg_id(
            app_id=app_id,
            sender_id=sender_id,
            timestamp=timestamp,
            text=raw_msg_id or text,
        )

    return ZaloEvent(
        msg_id=msg_id,
        event_name=event_name,
        sender_id=sender_id,
        text=text,
        timestamp=timestamp,
        derived_key=derived_key,
        payload=dict(payload),
    )
