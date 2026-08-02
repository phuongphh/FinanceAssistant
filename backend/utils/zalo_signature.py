"""Zalo OA webhook signature verification (Phase 5.0 #1.2).

The one place the ``X-ZEvent-Signature`` MAC is computed. Every constant
here traces back to a row in ``docs/conventions/zalo-operations.md``
§Platform facts — do not add a second implementation anywhere.

Phase 4B shipped this as ``HMAC-SHA256(secret, raw_body)``, which is not
what Zalo does. Zalo concatenates four strings and hashes the result::

    mac = sha256(app_id + data + timestamp + oa_secret_key)

where ``data`` is the raw request body **exactly as received** (any
re-serialisation changes the digest) and ``timestamp`` is the
``timestamp`` field from inside that body.

Because that formula is still ``ASSUMED`` in the facts table, this module
supports a log-only soak mode: :func:`verify` always reports the verdict,
and the caller decides whether a failed verdict rejects the request based
on ``ZALO_SIGNATURE_ENFORCE``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Header the MAC arrives in, and the prefix Zalo puts in front of the hex.
SIGNATURE_HEADER = "X-ZEvent-Signature"
_MAC_PREFIX = "mac="
# Some 4B-era tooling sent the digest with an HTTP-ish "sha256=" prefix.
# Accepting it costs nothing and avoids a spurious 403 during the soak.
_LEGACY_PREFIX = "sha256="


@dataclass(frozen=True)
class SignatureVerdict:
    """Outcome of one verification, including *why* it turned out that way.

    ``reason`` is a stable machine-readable slug so log-based alerting can
    tell "no secret configured" apart from "attacker sent garbage" without
    parsing prose.
    """

    valid: bool
    reason: str
    # True when verification did not actually run (dev bypass). Kept
    # separate from ``valid`` so a soak can't mistake a bypass for proof
    # that the formula is right.
    bypassed: bool = False


def compute_mac(
    *, app_id: str, raw_body: bytes, timestamp: str, oa_secret_key: str
) -> str:
    """Return the lowercase hex MAC for one webhook delivery.

    ``raw_body`` must be the bytes off the wire. Decoding is done with
    ``surrogateescape`` so a body that isn't valid UTF-8 still produces a
    deterministic digest instead of raising — a malformed body should end
    in a 403, not a 500.
    """
    data = raw_body.decode("utf-8", errors="surrogateescape")
    payload = f"{app_id}{data}{timestamp}{oa_secret_key}"
    return hashlib.sha256(
        payload.encode("utf-8", errors="surrogateescape")
    ).hexdigest()


def _normalize_header(signature_header: str) -> str:
    received = signature_header.strip()
    for prefix in (_MAC_PREFIX, _LEGACY_PREFIX):
        if received.lower().startswith(prefix):
            return received[len(prefix) :].strip()
    return received


def extract_timestamp(raw_body: bytes) -> str:
    """Pull the ``timestamp`` field out of the raw body.

    Returns ``""`` when the body isn't a JSON object or has no timestamp;
    the resulting MAC then simply won't match, which is the correct
    outcome for a body that doesn't look like a Zalo event.

    Zalo sends the timestamp as a string of epoch milliseconds, but some
    payloads carry it as a number. ``str()`` on an int round-trips
    identically; floats never appear in practice and would fail to match,
    which is again the safe direction.
    """
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    timestamp = payload.get("timestamp")
    if timestamp is None:
        return ""
    return timestamp if isinstance(timestamp, str) else str(timestamp)


def verify(
    *,
    raw_body: bytes,
    signature_header: str | None,
    app_id: str,
    oa_secret_key: str,
) -> SignatureVerdict:
    """Verify one webhook delivery.

    The dev bypass (empty ``oa_secret_key``) is only reachable when the
    channel is disabled — :func:`assert_startup_invariant` refuses to boot
    an enabled channel without a secret, so an enabled production channel
    can never take this branch.
    """
    if not oa_secret_key:
        return SignatureVerdict(
            valid=True, reason="no_secret_configured", bypassed=True
        )
    if not signature_header:
        return SignatureVerdict(valid=False, reason="missing_header")

    received = _normalize_header(signature_header)
    if not received:
        return SignatureVerdict(valid=False, reason="empty_header")

    timestamp = extract_timestamp(raw_body)
    if not timestamp:
        return SignatureVerdict(valid=False, reason="missing_timestamp")

    expected = compute_mac(
        app_id=app_id,
        raw_body=raw_body,
        timestamp=timestamp,
        oa_secret_key=oa_secret_key,
    )
    if hmac.compare_digest(received.lower(), expected):
        return SignatureVerdict(valid=True, reason="ok")
    return SignatureVerdict(valid=False, reason="mac_mismatch")


def assert_startup_invariant(
    *, channel_enabled: bool, oa_secret_key: str, app_id: str
) -> None:
    """Fail closed at boot rather than open at runtime.

    "Zalo channel on" plus "no secret to verify with" means anyone who
    finds the webhook URL can write to a messaging channel. There is no
    safe degraded mode for that combination, so the process refuses to
    start instead of silently accepting unauthenticated events.

    Raises:
        RuntimeError: when the channel is enabled but unverifiable.
    """
    if not channel_enabled:
        return
    missing = []
    if not oa_secret_key:
        missing.append("ZALO_OA_SECRET_KEY")
    if not app_id:
        missing.append("ZALO_APP_ID")
    if missing:
        raise RuntimeError(
            "ZALO_CHANNEL_ENABLED=true but "
            + ", ".join(missing)
            + " is empty — webhook signatures could not be verified. "
            "Set the secrets or disable the channel. "
            "See docs/conventions/zalo-operations.md#fail-closed-startup-invariant"
        )
