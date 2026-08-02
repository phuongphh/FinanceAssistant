"""Phase 5.0 #2.1 — inbound event identity and the surrogate dedup key.

The property under test is narrow but load-bearing: **a retry collides, a
genuine repeat does not**. Zalo re-delivers on any non-2xx, so a key that
is too loose double-charges the user's coffee and a key that is too tight
silently swallows their second one.

Tests are grouped by that split:

* ``parse_event`` reads the real payload shape and prefers Zalo's own
  ``message.msg_id``;
* the derived key changes with the timestamp (repeat) and not with
  anything we control (retry);
* unusable bodies return ``None`` rather than a guessed key, because an
  unidentifiable event cannot be safely processed twice.
"""

from __future__ import annotations

import hashlib

import pytest

from backend.utils import zalo_events
from backend.utils.zalo_events import parse_event

APP_ID = "app-1234"
SENDER = "zalo-user-9"
TIMESTAMP = "1754092800000"
TEXT = "ăn trưa 50k"


def _payload(**overrides):
    payload = {
        "app_id": APP_ID,
        "event_name": "user_send_text",
        "timestamp": TIMESTAMP,
        "sender": {"id": SENDER},
        "message": {"msg_id": "zalo-msg-1", "text": TEXT},
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------
# Reading the payload shape
# --------------------------------------------------------------------------


def test_zalo_msg_id_is_used_when_present():
    event = parse_event(_payload(), app_id=APP_ID)

    assert event is not None
    assert event.msg_id == "zalo-msg-1"
    assert event.derived_key is False
    assert event.sender_id == SENDER
    assert event.text == TEXT
    assert event.timestamp == TIMESTAMP
    assert event.event_name == "user_send_text"
    assert event.is_text is True


def test_payload_is_copied_not_aliased():
    """The worker re-reads the payload later; a shared dict would let the
    router's caller mutate what the worker sees."""
    original = _payload()
    event = parse_event(original, app_id=APP_ID)

    original["message"] = {"text": "tampered"}

    assert event is not None
    assert event.payload["message"]["text"] == TEXT


@pytest.mark.parametrize(
    "event_name,expected",
    [
        ("user_send_text", True),
        ("user_send_message", True),
        ("follow", False),
        ("unfollow", False),
        ("user_seen_message", False),
        ("", False),
    ],
)
def test_only_inbound_user_text_counts_as_text(event_name, expected):
    event = parse_event(_payload(event_name=event_name), app_id=APP_ID)

    assert event is not None
    assert event.is_text is expected


def test_numeric_timestamp_is_normalised_to_string():
    """Zalo documents a string; some payloads carry a number. The MAC helper
    already str()s it, so identity must agree or the two disagree on what
    'the same event' means."""
    event = parse_event(_payload(timestamp=1754092800000), app_id=APP_ID)

    assert event is not None
    assert event.timestamp == TIMESTAMP


def test_missing_message_block_is_not_a_crash():
    payload = _payload()
    payload.pop("message")

    event = parse_event(payload, app_id=APP_ID)

    assert event is not None
    assert event.text == ""
    assert event.derived_key is True


@pytest.mark.parametrize("bad_message", [None, "text", 42, ["a"]])
def test_non_object_message_block_is_treated_as_absent(bad_message):
    event = parse_event(_payload(message=bad_message), app_id=APP_ID)

    assert event is not None
    assert event.text == ""


@pytest.mark.parametrize("bad_sender", [None, "zalo-user-9", 42, ["a"]])
def test_non_object_sender_block_yields_no_event(bad_sender):
    """No sender id and no msg_id ⇒ nothing to dedup on."""
    payload = _payload(sender=bad_sender)
    payload["message"] = {"text": TEXT}

    assert parse_event(payload, app_id=APP_ID) is None


# --------------------------------------------------------------------------
# Surrogate key — the retry-vs-repeat property
# --------------------------------------------------------------------------


def _derived(**overrides):
    payload = _payload(**overrides)
    payload["message"] = {"text": payload["message"].get("text", TEXT)}
    event = parse_event(payload, app_id=APP_ID)
    assert event is not None
    return event


def test_surrogate_is_used_when_zalo_sends_no_msg_id():
    event = _derived()

    assert event.derived_key is True
    assert event.msg_id.startswith(zalo_events.DERIVED_PREFIX)


def test_surrogate_matches_the_documented_formula():
    """Pinned so the key can't drift silently — a changed formula makes every
    in-flight retry look brand new for one deploy."""
    expected_digest = hashlib.sha256(
        f"{APP_ID}|{SENDER}|{TIMESTAMP}|{TEXT}".encode("utf-8")
    ).hexdigest()

    assert _derived().msg_id == f"{zalo_events.DERIVED_PREFIX}{expected_digest}"


def test_a_retry_of_the_same_delivery_collides():
    """The whole point: Zalo re-posts an identical body, we must recognise it."""
    assert _derived().msg_id == _derived().msg_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"timestamp": "1754092800001"},
        {"sender": {"id": "someone-else"}},
        {"message": {"text": "cà phê 30k"}},
    ],
    ids=["one_ms_later", "other_sender", "other_text"],
)
def test_a_genuinely_different_message_does_not_collide(overrides):
    assert _derived().msg_id != _derived(**overrides).msg_id


def test_the_same_text_a_second_later_is_captured_twice():
    """Two coffees, two rows. Timestamps are epoch *milliseconds*, so even
    back-to-back sends separate."""
    first = _derived()
    second = _derived(timestamp=str(int(TIMESTAMP) + 1000))

    assert first.msg_id != second.msg_id


def test_app_id_is_part_of_the_key():
    """Two OAs sharing a database must not collide on message identity."""
    payload = _payload()
    payload["message"] = {"text": TEXT}

    a = parse_event(payload, app_id="app-1234")
    b = parse_event(payload, app_id="app-9999")

    assert a is not None and b is not None
    assert a.msg_id != b.msg_id


def test_field_boundaries_cannot_be_shifted():
    """Without a separator, sender 'ab'+ts 'c' and sender 'a'+ts 'bc' would
    hash identically and one user could suppress another's message."""
    left = zalo_events.derive_msg_id(
        app_id=APP_ID, sender_id="ab", timestamp="c", text=TEXT
    )
    right = zalo_events.derive_msg_id(
        app_id=APP_ID, sender_id="a", timestamp="bc", text=TEXT
    )

    assert left != right


def test_a_derived_key_can_never_collide_with_a_zalo_id():
    """A bare hex digest arriving as a real msg_id must stay distinct from a
    surrogate that happens to hash to the same value."""
    digest = hashlib.sha256(b"whatever").hexdigest()
    event = parse_event(
        _payload(message={"msg_id": digest, "text": TEXT}), app_id=APP_ID
    )

    assert event is not None
    assert event.msg_id == digest
    assert not event.msg_id.startswith(zalo_events.DERIVED_PREFIX)


# --------------------------------------------------------------------------
# Column safety and unusable bodies
# --------------------------------------------------------------------------


def test_an_oversized_msg_id_is_folded_into_a_surrogate():
    """``zalo_updates.msg_id`` is String(128). An overlong id would fail the
    INSERT, 500 the webhook, and make Zalo retry it forever."""
    huge = "x" * (zalo_events.MAX_KEY_LENGTH + 1)

    event = parse_event(_payload(message={"msg_id": huge, "text": TEXT}), app_id=APP_ID)

    assert event is not None
    assert event.derived_key is True
    assert len(event.msg_id) <= zalo_events.MAX_KEY_LENGTH


def test_two_different_oversized_ids_still_differ():
    a = parse_event(
        _payload(message={"msg_id": "a" * 200, "text": TEXT}), app_id=APP_ID
    )
    b = parse_event(
        _payload(message={"msg_id": "b" * 200, "text": TEXT}), app_id=APP_ID
    )

    assert a is not None and b is not None
    assert a.msg_id != b.msg_id


def test_every_key_fits_the_column():
    event = _derived()

    assert len(event.msg_id) <= zalo_events.MAX_KEY_LENGTH


@pytest.mark.parametrize(
    "body", [None, "not a dict", 42, [], ["user_send_text"]], ids=type
)
def test_non_object_bodies_yield_no_event(body):
    assert parse_event(body, app_id=APP_ID) is None


def test_missing_timestamp_yields_no_event():
    """Without a timestamp the surrogate loses its only time component, so
    every repeat would be swallowed as a retry. Refuse instead of guessing."""
    payload = _payload()
    payload.pop("timestamp")
    payload["message"] = {"text": TEXT}

    assert parse_event(payload, app_id=APP_ID) is None


def test_missing_timestamp_is_fine_when_zalo_supplies_a_msg_id():
    """The timestamp only matters to the surrogate."""
    payload = _payload()
    payload.pop("timestamp")

    event = parse_event(payload, app_id=APP_ID)

    assert event is not None
    assert event.msg_id == "zalo-msg-1"


def test_empty_body_yields_no_event():
    assert parse_event({}, app_id=APP_ID) is None


def test_boolean_fields_are_treated_as_absent():
    """A bool is an int in Python; ``str(True)`` would smuggle 'True' into the
    key material and make two unrelated malformed bodies collide."""
    payload = _payload(timestamp=True)
    payload["message"] = {"text": TEXT}

    assert parse_event(payload, app_id=APP_ID) is None
