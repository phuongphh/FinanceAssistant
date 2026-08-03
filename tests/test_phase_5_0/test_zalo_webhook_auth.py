"""Phase 5.0 #1.2 — webhook-level behaviour of signature verification.

Covers the three states the operator can put the endpoint in:

* secret set + ``ZALO_SIGNATURE_ENFORCE=true``  → bad MAC is a 403
* secret set + ``ZALO_SIGNATURE_ENFORCE=false`` → bad MAC is logged, request
  still processed (the soak window, see
  docs/conventions/zalo-operations.md#signature-soak-rollout)
* no secret (dev)                               → verification skipped

Plus the invariant that a rejection never leaks who was targeted.
"""

from __future__ import annotations

import hashlib
import json
import logging

import pytest

pytest.importorskip("fastapi")

# noqa: E402 below — imports must follow the importorskip guard above.
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.database import get_db  # noqa: E402
from backend.routers import zalo as zalo_router  # noqa: E402

APP_ID = "app-1234"
SECRET = "oa-secret-key"
TIMESTAMP = "1754092800000"
SENDER_ID = "zalo-sender-should-never-be-logged"


def _raw_body(text: str = "xin chào") -> bytes:
    return json.dumps(
        {
            "app_id": APP_ID,
            "event_name": "user_send_text",
            "timestamp": TIMESTAMP,
            "sender": {"id": SENDER_ID},
            "message": {"msg_id": "m-1", "text": text},
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _mac(raw: bytes, secret: str = SECRET) -> str:
    data = raw.decode("utf-8")
    return hashlib.sha256(
        f"{APP_ID}{data}{TIMESTAMP}{secret}".encode("utf-8")
    ).hexdigest()


class _StubSession:
    """Just enough AsyncSession for the router's commit at the boundary."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture()
def handled(monkeypatch) -> list[dict]:
    """Stub out the two side-effecting steps of the route.

    The router's job after a successful MAC check is: claim the msg_id,
    then enqueue a background task. Both are replaced here so these
    tests exercise *only* signature handling — no DB, no event loop task
    left running after the assertion. What lands in the returned list is
    what would have been handed to the worker.
    """
    calls: list[dict] = []

    async def _fake_claim(db, event) -> bool:
        return True

    def _fake_enqueue(msg_id: str, payload: dict) -> None:
        calls.append({"msg_id": msg_id, "payload": payload})

    monkeypatch.setattr(zalo_router, "_claim_update", _fake_claim)
    monkeypatch.setattr(zalo_router, "_enqueue_event", _fake_enqueue)
    return calls


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(zalo_router.router, prefix="/api/v1")

    async def _fake_db():
        yield _StubSession()

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


@pytest.fixture()
def zalo_settings(monkeypatch):
    """Configure the (lru_cached) Settings object for one test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "zalo_app_id", APP_ID)
    monkeypatch.setattr(settings, "zalo_oa_secret_key", SECRET)
    monkeypatch.setattr(settings, "zalo_signature_enforce", True)
    return settings


def _post(client: TestClient, raw: bytes, signature: str | None):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-ZEvent-Signature"] = signature
    return client.post("/api/v1/zalo/webhook", content=raw, headers=headers)


# --------------------------------------------------------------------------
# enforce = True
# --------------------------------------------------------------------------


def test_valid_signature_is_processed(client, zalo_settings, handled):
    raw = _raw_body()
    resp = _post(client, raw, "mac=" + _mac(raw))

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert len(handled) == 1
    assert handled[0]["msg_id"] == "m-1"
    assert handled[0]["payload"]["message"]["text"] == "xin chào"
    assert handled[0]["payload"]["sender"]["id"] == SENDER_ID


def test_invalid_signature_is_rejected_with_403(client, zalo_settings, handled):
    raw = _raw_body()
    resp = _post(client, raw, "mac=" + _mac(raw, secret="attacker"))

    assert resp.status_code == 403
    assert handled == []


def test_missing_signature_header_is_rejected(client, zalo_settings, handled):
    resp = _post(client, _raw_body(), None)

    assert resp.status_code == 403
    assert handled == []


def test_tampered_body_is_rejected(client, zalo_settings, handled):
    """MAC captured from one message must not authorise a different one."""
    signature = "mac=" + _mac(_raw_body("ăn trưa 50k"))
    resp = _post(client, _raw_body("chuyển 10 triệu"), signature)

    assert resp.status_code == 403
    assert handled == []


def test_rejection_logs_never_leak_sender_or_body(
    client, zalo_settings, handled, caplog
):
    raw = _raw_body()
    with caplog.at_level(logging.DEBUG):
        resp = _post(client, raw, "mac=" + _mac(raw, secret="attacker"))

    assert resp.status_code == 403
    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert SENDER_ID not in blob
    assert "xin chào" not in blob
    assert SECRET not in blob
    # ...but the reason slug the alerting rule keys on must be there.
    assert "mac_mismatch" in blob


def test_verdict_is_logged_for_the_soak_counter(client, zalo_settings, handled, caplog):
    raw = _raw_body()
    with caplog.at_level(logging.INFO):
        _post(client, raw, "mac=" + _mac(raw))

    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert "zalo.signature valid=True reason=ok" in blob


# --------------------------------------------------------------------------
# enforce = False — the soak window
# --------------------------------------------------------------------------


def test_soak_mode_accepts_bad_signature_but_logs_it(
    client, zalo_settings, handled, monkeypatch, caplog
):
    monkeypatch.setattr(zalo_settings, "zalo_signature_enforce", False)
    raw = _raw_body()

    with caplog.at_level(logging.INFO):
        resp = _post(client, raw, "mac=" + _mac(raw, secret="attacker"))

    assert resp.status_code == 200
    assert len(handled) == 1
    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert "valid=False reason=mac_mismatch" in blob
    assert "soak mode" in blob


def test_soak_mode_still_reports_valid_signatures_as_valid(
    client, zalo_settings, handled, monkeypatch, caplog
):
    """The soak is only meaningful if a correct MAC reads as valid=True."""
    monkeypatch.setattr(zalo_settings, "zalo_signature_enforce", False)
    raw = _raw_body()

    with caplog.at_level(logging.INFO):
        resp = _post(client, raw, "mac=" + _mac(raw))

    assert resp.status_code == 200
    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert "valid=True reason=ok" in blob
    assert "bypassed=False" in blob


# --------------------------------------------------------------------------
# no secret — dev bypass
# --------------------------------------------------------------------------


def test_no_secret_skips_verification_and_marks_it_bypassed(
    client, zalo_settings, handled, monkeypatch, caplog
):
    monkeypatch.setattr(zalo_settings, "zalo_oa_secret_key", "")

    with caplog.at_level(logging.INFO):
        resp = _post(client, _raw_body(), None)

    assert resp.status_code == 200
    assert len(handled) == 1
    blob = "\n".join(record.getMessage() for record in caplog.records)
    # bypassed must be distinguishable from a genuine pass, otherwise a dev
    # deployment would look like 24h of successful soak traffic.
    assert "bypassed=True" in blob


# --------------------------------------------------------------------------
# non-event payloads still short-circuit safely
# --------------------------------------------------------------------------


def test_malformed_json_with_no_signature_is_rejected(client, zalo_settings, handled):
    """No timestamp to hash → the MAC can't match → 403, not a 500."""
    resp = _post(client, b"\xff\xfe not json", "mac=" + "0" * 64)

    assert resp.status_code == 403
    assert handled == []


def test_unrelated_event_returns_200_without_handling(client, zalo_settings, handled):
    raw = json.dumps(
        {
            "app_id": APP_ID,
            "event_name": "follow",
            "timestamp": TIMESTAMP,
            "sender": {"id": SENDER_ID},
        }
    ).encode("utf-8")
    resp = _post(client, raw, "mac=" + _mac(raw))

    assert resp.status_code == 200
    assert handled == []
