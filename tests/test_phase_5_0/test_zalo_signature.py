"""Phase 5.0 #1.2 — Zalo webhook signature verification.

Phase 4B shipped ``HMAC-SHA256(secret, raw_body)``, which is not the MAC
Zalo sends. With a secret configured in prod, 100% of webhooks would have
been rejected. These tests pin the real formula::

    mac = sha256(app_id + data + timestamp + oa_secret_key)

``data`` is the body **exactly as received** — the re-serialisation test
below is the one that would have caught a "parse then re-dump" regression.

The formula is still marked ASSUMED in
``docs/conventions/zalo-operations.md`` (Zalo's docs are not fetchable from
CI), which is precisely why ``ZALO_SIGNATURE_ENFORCE`` exists and why the
soak-mode behaviour is tested here rather than assumed.
"""

from __future__ import annotations

import hashlib
import json
import logging

import pytest

from backend.utils import zalo_signature

APP_ID = "app-1234"
SECRET = "oa-secret-key"
TIMESTAMP = "1754092800000"


def _body(**extra) -> bytes:
    payload = {
        "app_id": APP_ID,
        "event_name": "user_send_text",
        "timestamp": TIMESTAMP,
        "sender": {"id": "zalo-user-9"},
        "message": {"msg_id": "m-1", "text": "ăn trưa 50k"},
        **extra,
    }
    # ensure_ascii=False so the body carries real multi-byte UTF-8 — the
    # digest must be taken over the encoded bytes, not over a \u-escaped
    # ASCII approximation.
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _expected_mac(raw: bytes, *, app_id: str = APP_ID, secret: str = SECRET) -> str:
    data = raw.decode("utf-8")
    return hashlib.sha256(
        f"{app_id}{data}{TIMESTAMP}{secret}".encode("utf-8")
    ).hexdigest()


# --------------------------------------------------------------------------
# compute_mac
# --------------------------------------------------------------------------


def test_compute_mac_matches_hand_built_vector():
    """Independent reimplementation of the concatenation must agree."""
    raw = _body()
    assert zalo_signature.compute_mac(
        app_id=APP_ID,
        raw_body=raw,
        timestamp=TIMESTAMP,
        oa_secret_key=SECRET,
    ) == _expected_mac(raw)


def test_compute_mac_is_not_hmac_over_body():
    """Guard against a revert to the Phase 4B formula."""
    import hmac

    raw = _body()
    legacy = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert (
        zalo_signature.compute_mac(
            app_id=APP_ID, raw_body=raw, timestamp=TIMESTAMP, oa_secret_key=SECRET
        )
        != legacy
    )


def test_compute_mac_is_byte_exact_over_body():
    """Re-serialising the JSON changes the digest — so we never may."""
    raw = _body()
    reserialised = json.dumps(json.loads(raw), ensure_ascii=True).encode("utf-8")
    assert reserialised != raw

    mac_raw = zalo_signature.compute_mac(
        app_id=APP_ID, raw_body=raw, timestamp=TIMESTAMP, oa_secret_key=SECRET
    )
    mac_reserialised = zalo_signature.compute_mac(
        app_id=APP_ID,
        raw_body=reserialised,
        timestamp=TIMESTAMP,
        oa_secret_key=SECRET,
    )
    assert mac_raw != mac_reserialised


def test_compute_mac_survives_non_utf8_body():
    """A malformed body must produce a digest, not a 500."""
    mac = zalo_signature.compute_mac(
        app_id=APP_ID,
        raw_body=b"\xff\xfe not utf-8",
        timestamp=TIMESTAMP,
        oa_secret_key=SECRET,
    )
    assert len(mac) == 64


# --------------------------------------------------------------------------
# extract_timestamp
# --------------------------------------------------------------------------


def test_extract_timestamp_reads_string_field():
    assert zalo_signature.extract_timestamp(_body()) == TIMESTAMP


def test_extract_timestamp_stringifies_numeric_field():
    raw = json.dumps({"timestamp": int(TIMESTAMP)}).encode()
    assert zalo_signature.extract_timestamp(raw) == TIMESTAMP


@pytest.mark.parametrize(
    "raw",
    [
        b"not json at all",
        b"[1, 2, 3]",  # JSON, but not an object
        b'{"event_name": "user_send_text"}',  # object, no timestamp
        b"",
    ],
)
def test_extract_timestamp_returns_empty_for_unusable_body(raw: bytes):
    assert zalo_signature.extract_timestamp(raw) == ""


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", ["mac=", "sha256=", "", "MAC="])
def test_verify_accepts_each_header_prefix(prefix: str):
    raw = _body()
    verdict = zalo_signature.verify(
        raw_body=raw,
        signature_header=f"{prefix}{_expected_mac(raw)}",
        app_id=APP_ID,
        oa_secret_key=SECRET,
    )
    assert verdict.valid is True
    assert verdict.reason == "ok"
    assert verdict.bypassed is False


def test_verify_accepts_uppercase_hex():
    raw = _body()
    verdict = zalo_signature.verify(
        raw_body=raw,
        signature_header="mac=" + _expected_mac(raw).upper(),
        app_id=APP_ID,
        oa_secret_key=SECRET,
    )
    assert verdict.valid is True


def test_verify_rejects_wrong_secret():
    raw = _body()
    verdict = zalo_signature.verify(
        raw_body=raw,
        signature_header=_expected_mac(raw, secret="wrong-secret"),
        app_id=APP_ID,
        oa_secret_key=SECRET,
    )
    assert verdict.valid is False
    assert verdict.reason == "mac_mismatch"


def test_verify_rejects_wrong_app_id():
    """app_id is part of the MAC, so a mismatched app must not validate."""
    raw = _body()
    verdict = zalo_signature.verify(
        raw_body=raw,
        signature_header=_expected_mac(raw, app_id="other-app"),
        app_id=APP_ID,
        oa_secret_key=SECRET,
    )
    assert verdict.valid is False
    assert verdict.reason == "mac_mismatch"


def test_verify_rejects_replay_with_different_timestamp():
    """A captured MAC does not validate against a re-timestamped body."""
    raw = _body()
    mac = _expected_mac(raw)
    replayed = _body(timestamp="1754092900000")
    verdict = zalo_signature.verify(
        raw_body=replayed,
        signature_header=mac,
        app_id=APP_ID,
        oa_secret_key=SECRET,
    )
    assert verdict.valid is False
    assert verdict.reason == "mac_mismatch"


def test_verify_rejects_missing_header():
    verdict = zalo_signature.verify(
        raw_body=_body(),
        signature_header=None,
        app_id=APP_ID,
        oa_secret_key=SECRET,
    )
    assert verdict.valid is False
    assert verdict.reason == "missing_header"


def test_verify_rejects_empty_header_value():
    verdict = zalo_signature.verify(
        raw_body=_body(),
        signature_header="mac=",
        app_id=APP_ID,
        oa_secret_key=SECRET,
    )
    assert verdict.valid is False
    assert verdict.reason == "empty_header"


def test_verify_rejects_body_without_timestamp():
    verdict = zalo_signature.verify(
        raw_body=b'{"event_name": "user_send_text"}',
        signature_header="mac=" + "0" * 64,
        app_id=APP_ID,
        oa_secret_key=SECRET,
    )
    assert verdict.valid is False
    assert verdict.reason == "missing_timestamp"


def test_verify_bypasses_only_when_secret_is_empty():
    verdict = zalo_signature.verify(
        raw_body=_body(),
        signature_header=None,
        app_id=APP_ID,
        oa_secret_key="",
    )
    assert verdict.valid is True
    assert verdict.bypassed is True
    assert verdict.reason == "no_secret_configured"


def test_verdict_is_immutable():
    """Callers must not be able to talk a failed verdict into passing."""
    verdict = zalo_signature.SignatureVerdict(valid=False, reason="mac_mismatch")
    with pytest.raises(Exception):
        verdict.valid = True  # type: ignore[misc]


# --------------------------------------------------------------------------
# assert_startup_invariant — fail closed
# --------------------------------------------------------------------------


def test_startup_invariant_allows_disabled_channel_without_secrets():
    zalo_signature.assert_startup_invariant(
        channel_enabled=False, oa_secret_key="", app_id=""
    )


def test_startup_invariant_allows_enabled_channel_with_secrets():
    zalo_signature.assert_startup_invariant(
        channel_enabled=True, oa_secret_key=SECRET, app_id=APP_ID
    )


@pytest.mark.parametrize(
    ("secret", "app_id", "expected"),
    [
        ("", APP_ID, "ZALO_OA_SECRET_KEY"),
        (SECRET, "", "ZALO_APP_ID"),
    ],
)
def test_startup_invariant_names_the_missing_secret(
    secret: str, app_id: str, expected: str
):
    with pytest.raises(RuntimeError) as exc:
        zalo_signature.assert_startup_invariant(
            channel_enabled=True, oa_secret_key=secret, app_id=app_id
        )
    assert expected in str(exc.value)


def test_startup_invariant_lists_every_missing_secret():
    with pytest.raises(RuntimeError) as exc:
        zalo_signature.assert_startup_invariant(
            channel_enabled=True, oa_secret_key="", app_id=""
        )
    message = str(exc.value)
    assert "ZALO_OA_SECRET_KEY" in message
    assert "ZALO_APP_ID" in message


def test_startup_invariant_error_never_leaks_the_secret(caplog):
    """The failure message points at a runbook; it must not echo values."""
    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(RuntimeError) as exc:
            zalo_signature.assert_startup_invariant(
                channel_enabled=True, oa_secret_key="", app_id="super-secret-app-id"
            )
    assert "super-secret-app-id" not in str(exc.value)
