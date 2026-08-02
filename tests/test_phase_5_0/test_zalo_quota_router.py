"""Operator surface for the send ledger (Phase 5.0 #3.3).

``backend/services/zalo_quota_metrics.py`` is covered by its own suite;
this file is about the *edge* — the three things a router owns that a
pure function can't be asked about:

* **who may read it.** The snapshot names a third party's quota and our
  own delivery volume. It is mounted whether or not
  ``ZALO_CHANNEL_ENABLED`` is on (it is the instrument you read while
  deciding to flip the flag), so its only protection is
  ``INTERNAL_API_KEY``. An unset key must lock the endpoint, not open it.
* **what a typo does.** The baseline arrives as two query params the
  operator copy-pastes out of a runbook. Half a baseline, a mangled
  timestamp, or a clock-skewed future one must come back as a 400 the
  operator can read, never as a snapshot that silently reports
  ``need_baseline`` — which reads as a system fault instead of a fixable
  mistake.
* **what an outage does.** This endpoint exists to explain incidents, so
  it must survive one: a quota read that fails, or a channel that isn't
  configured at all, degrades to ``zalo_quota: null`` plus honest
  internal counters. A 500 here would blind the operator exactly when
  they are looking.

No database and no socket: ``get_db`` is overridden with the same
``FakeMetricsSession`` the service suite uses, and the OA client is
stubbed at the router's own module attribute.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

# noqa: E402 below — imports must follow the importorskip guard above.
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.database import get_db  # noqa: E402
from backend.routers import admin_zalo_quota as mod  # noqa: E402
from backend.services import zalo_quota_metrics as metrics  # noqa: E402
from backend.services import zalo_window_service as svc  # noqa: E402
from tests.test_phase_5_0.conftest import FakeMetricsSession  # noqa: E402

API_KEY = "internal-key-for-tests"
BASE = "/api/v1/admin/zalo-quota"


class _FakeOAClient:
    """The quota half of :class:`ZaloOAClient`, without a socket.

    ``error`` models the case the real client is documented *not* to
    produce (it collapses every failure to ``None``) — the router still
    catches it, because a diagnostic endpoint that 500s during an
    incident is worse than one that says "quota unavailable".
    """

    def __init__(
        self,
        *,
        configured: bool = True,
        quota: dict | None = None,
        error: Exception | None = None,
    ) -> None:
        self.is_configured = configured
        self._quota = quota
        self._error = error
        self.calls = 0

    async def get_message_quota(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._quota


@pytest.fixture()
def db() -> FakeMetricsSession:
    """One read-only session, inspectable after the request."""
    return FakeMetricsSession(
        blocked={svc.REASON_QUOTA_EXHAUSTED: 2},
        delivered=10,
        ledger={"tracked_senders": 3, "open_windows": 2, "slots_used_open": 5},
    )


@pytest.fixture()
def client(db) -> TestClient:
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/v1")

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


@pytest.fixture()
def admin_key(monkeypatch):
    """Configure the (lru_cached) Settings object for one test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "internal_api_key", API_KEY)
    monkeypatch.setattr(settings, "zalo_channel_enabled", True)
    return settings


@pytest.fixture()
def oa(monkeypatch):
    """Install a stub OA client; returns an installer for the variants."""

    def _install(**kwargs) -> _FakeOAClient:
        client = _FakeOAClient(**kwargs)
        monkeypatch.setattr(mod, "get_zalo_oa_client", lambda: client)
        return client

    _install(quota={"remain": 400, "total": 500})
    return _install


def _get(client: TestClient, path: str, *, key: str | None = API_KEY, **params):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(f"{BASE}{path}", headers=headers, params=params)


def _iso(hours_ago: float = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


# --------------------------------------------------------------------------
# Authentication — the only thing between this and the public internet
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/baseline", "/snapshot"])
def test_both_endpoints_require_the_admin_key(client, admin_key, oa, path):
    assert _get(client, path, key=None).status_code == 403


@pytest.mark.parametrize("path", ["/baseline", "/snapshot"])
def test_a_wrong_key_is_rejected(client, admin_key, oa, path):
    assert _get(client, path, key="not-the-key").status_code == 403


@pytest.mark.parametrize("path", ["/baseline", "/snapshot"])
def test_an_unconfigured_admin_key_locks_the_endpoint(
    client, monkeypatch, oa, path
):
    # Fail closed: a deploy that forgot INTERNAL_API_KEY must not publish
    # delivery volumes to anyone who finds the URL. 503 (not 403) so the
    # operator can tell "you're not allowed" from "nobody is, fix config".
    monkeypatch.setattr(get_settings(), "internal_api_key", "")

    assert _get(client, path, key=None).status_code == 503
    assert _get(client, path, key="anything").status_code == 503


def test_an_unauthenticated_call_never_reaches_the_database_or_zalo(
    client, admin_key, oa, db
):
    stub = oa(quota={"remain": 1, "total": 8})

    _get(client, "/snapshot", key=None)

    assert stub.calls == 0
    assert db.statements == []


# --------------------------------------------------------------------------
# GET /baseline — step 1 of the reconciliation procedure
# --------------------------------------------------------------------------


def test_baseline_returns_exactly_what_snapshot_asks_back_for(
    client, admin_key, oa
):
    oa(quota={"remain": 431, "total": 500})

    body = _get(client, "/baseline").json()

    assert body["remain"] == 431
    assert body["total"] == 500
    # The runbook step is a copy-paste, not a clock lookup the operator
    # has to get right — so the timestamp must parse back the same way
    # /snapshot will parse it.
    assert metrics.parse_baseline_at(body["captured_at"]) is not None
    assert body["channel_enabled"] is True


def test_an_unreadable_baseline_is_null_rather_than_a_guess(
    client, admin_key, oa
):
    # A baseline captured from an unknown is not a baseline: the operator
    # must be able to see that and retry, not save a zero.
    oa(quota=None)

    body = _get(client, "/baseline").json()

    assert body["remain"] is None
    assert body["total"] is None


def test_an_unconfigured_channel_skips_the_call_entirely(client, admin_key, oa):
    stub = oa(configured=False, quota={"remain": 9, "total": 9})

    body = _get(client, "/baseline").json()

    assert stub.calls == 0
    assert body["remain"] is None


def test_a_raising_client_still_answers(client, admin_key, oa):
    oa(error=RuntimeError("connection reset"))

    resp = _get(client, "/baseline")

    assert resp.status_code == 200
    assert resp.json()["remain"] is None


# --------------------------------------------------------------------------
# GET /snapshot — validation of the operator-supplied baseline
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"baseline_remain": 400},
        {"baseline_at": "2026-08-01T00:00:00Z"},
    ],
    ids=["remain-only", "at-only"],
)
def test_half_a_baseline_is_rejected(client, admin_key, oa, params):
    # Honouring half of it would compare Zalo's movement over an unknown
    # interval against ours over 24 hours, and report the difference as
    # drift.
    resp = _get(client, "/snapshot", **params)

    assert resp.status_code == 400
    assert "together" in resp.json()["detail"]


@pytest.mark.parametrize("bad", ["yesterday", "", "2026-13-99"])
def test_an_unparseable_baseline_timestamp_is_a_readable_error(
    client, admin_key, oa, bad
):
    resp = _get(client, "/snapshot", baseline_remain=400, baseline_at=bad)

    assert resp.status_code == 400
    assert "ISO-8601" in resp.json()["detail"]


def test_a_future_baseline_is_rejected(client, admin_key, oa):
    # Clock skew or a mistyped date. Either way the interval is negative
    # and every number derived from it is nonsense.
    resp = _get(
        client, "/snapshot", baseline_remain=400, baseline_at=_iso(hours_ago=-2)
    )

    assert resp.status_code == 400
    assert "future" in resp.json()["detail"]


def test_a_negative_baseline_remain_is_rejected_by_the_schema(
    client, admin_key, oa
):
    assert _get(
        client, "/snapshot", baseline_remain=-1, baseline_at=_iso()
    ).status_code == 422


@pytest.mark.parametrize("hours", [0, -3, 24 * 7 + 1])
def test_the_lookback_is_bounded(client, admin_key, oa, hours):
    # Below an hour the interval says nothing; past a week the events
    # scan stops being cheap.
    assert _get(client, "/snapshot", hours=hours).status_code == 422


@pytest.mark.parametrize("hours", [mod.MIN_LOOKBACK_HOURS, mod.MAX_LOOKBACK_HOURS])
def test_the_bounds_themselves_are_allowed(client, admin_key, oa, hours):
    assert _get(client, "/snapshot", hours=hours).status_code == 200


def test_a_rejected_request_never_queries(client, admin_key, oa, db):
    _get(client, "/snapshot", baseline_remain=400, baseline_at="nonsense")

    assert db.statements == []


# --------------------------------------------------------------------------
# GET /snapshot — the reported body
# --------------------------------------------------------------------------


def test_a_snapshot_carries_the_counters_and_the_flag_state(
    client, admin_key, oa, db
):
    body = _get(client, "/snapshot").json()

    assert body["delivered"] == 10
    assert body["blocked_total"] == 2
    assert body["attempts"] == 12
    # Every reason gets a row even at zero, so a dashboard panel doesn't
    # vanish on a quiet day and get read as "nothing is blocked".
    assert set(body["blocked_by_reason"]) == set(svc.BLOCK_REASONS)
    assert body["window_ledger"]["tracked_senders"] == 3
    assert body["channel_enabled"] is True
    assert body["quota_read_attempted"] is True
    assert body["zalo_quota"] == {"remain": 400, "total": 500}


def test_the_snapshot_is_read_only(client, admin_key, oa, db):
    _get(client, "/snapshot")

    assert db.commits == 0


def test_the_lookback_reaches_the_query(client, admin_key, oa, db):
    _get(client, "/snapshot", hours=3)

    since = db.delivered_since[0]
    # The router stamps its clock before this line runs, so the interval
    # is 3h plus a hair — bounded above rather than pinned exactly.
    elapsed = datetime.now(timezone.utc) - since
    assert timedelta(hours=3) <= elapsed < timedelta(hours=3, minutes=1)


def test_read_quota_false_answers_without_touching_zalo(client, admin_key, oa, db):
    # The counters are what an operator refreshes repeatedly during an
    # incident; each refresh must not cost a round trip to a third party
    # that rate-limits us.
    stub = oa(quota={"remain": 400, "total": 500})

    body = _get(client, "/snapshot", read_quota="false").json()

    assert stub.calls == 0
    assert body["zalo_quota"] is None
    assert body["quota_read_attempted"] is False
    # The internal half is still fully reported.
    assert body["delivered"] == 10


def test_skipping_the_quota_read_is_reported_as_unavailable_not_as_agreement(
    client, admin_key, oa
):
    body = _get(
        client,
        "/snapshot",
        read_quota="false",
        baseline_remain=400,
        baseline_at=_iso(),
    ).json()

    assert body["reconciliation"]["comparable"] is False
    assert body["reconciliation"]["status"] == metrics.RECONCILE_QUOTA_UNAVAILABLE
    assert body["reconciliation"]["drift"] is None


def test_a_failed_quota_read_degrades_instead_of_five_hundreding(
    client, admin_key, oa
):
    oa(error=RuntimeError("upstream 502"))

    resp = _get(client, "/snapshot", baseline_remain=400, baseline_at=_iso())
    body = resp.json()

    assert resp.status_code == 200
    assert body["zalo_quota"] is None
    # quota_read_attempted stays true: we tried and failed, which is a
    # different situation from ?read_quota=false and is what tells the
    # operator to look at the Zalo side.
    assert body["quota_read_attempted"] is True
    assert body["reconciliation"]["status"] == metrics.RECONCILE_QUOTA_UNAVAILABLE
    assert "zalo_quota_unavailable" in {a["code"] for a in body["alerts"]}


def test_a_quota_outage_never_reports_a_drift_number(client, admin_key, oa):
    # The two wrong answers an outage could produce: a silent zero, or a
    # drift equal to everything we sent. Neither may appear.
    oa(quota=None)

    body = _get(client, "/snapshot", baseline_remain=400, baseline_at=_iso()).json()

    assert body["reconciliation"]["drift"] is None
    assert "zalo_quota_drift" not in {a["code"] for a in body["alerts"]}


# --------------------------------------------------------------------------
# GET /snapshot — reconciliation end to end
# --------------------------------------------------------------------------


def test_agreeing_movements_reconcile_and_raise_nothing(
    client, admin_key, oa, db
):
    # Zalo consumed 10 (410 → 400) over the baseline interval; so did we.
    db.delivered = [10, 10]
    oa(quota={"remain": 400, "total": 500})

    body = _get(client, "/snapshot", baseline_remain=410, baseline_at=_iso()).json()

    assert body["reconciliation"]["comparable"] is True
    assert body["reconciliation"]["drift"] == 0
    assert body["alerts"] == []


def test_a_disagreement_past_the_tolerance_is_alerted_with_the_runbook(
    client, admin_key, oa, db
):
    # Zalo consumed 10, we believe we sent 3 — seven sends we have no
    # record of, which is the case #3.3 exists to catch.
    db.delivered = [3, 3]
    oa(quota={"remain": 400, "total": 500})

    body = _get(client, "/snapshot", baseline_remain=410, baseline_at=_iso()).json()

    assert body["reconciliation"]["drift"] == 7
    alert = next(a for a in body["alerts"] if a["code"] == "zalo_quota_drift")
    assert "zalo-operations.md" in alert["message"]


def test_the_baseline_is_compared_over_its_own_interval(
    client, admin_key, oa, db
):
    # 4 delivered in the last hour, 30 in the 24h lookback. Reconciling
    # against the 24h figure would invent a drift of 26 out of the
    # interval mismatch alone.
    db.delivered = [30, 4]
    oa(quota={"remain": 400, "total": 500})

    body = _get(client, "/snapshot", baseline_remain=404, baseline_at=_iso()).json()

    assert body["delivered"] == 30
    assert body["baseline"]["delivered_since"] == 4
    assert body["reconciliation"]["drift"] == 0
    assert len(db.delivered_since) == 2


def test_without_a_baseline_the_counters_still_render(client, admin_key, oa, db):
    body = _get(client, "/snapshot").json()

    assert body["reconciliation"]["status"] == metrics.RECONCILE_NEED_BASELINE
    assert body["delivered"] == 10
    # Only the reconciliation degrades — one query, not two.
    assert len(db.delivered_since) == 1


# --------------------------------------------------------------------------
# The endpoint is a diagnostic, not a leak
# --------------------------------------------------------------------------


def test_the_snapshot_reports_counts_and_never_an_identity(client, admin_key, oa):
    # Checked on the *values*, not the field names: ``tracked_senders`` is
    # a legitimate count, and a substring scan would both flag it and miss
    # an id smuggled into a value.
    body = _get(client, "/snapshot").json()

    for key in ("zalo_user_id", "sender", "sender_id", "user_id", "phone"):
        assert key not in body

    ledger = {k: v for k, v in body["window_ledger"].items() if k != "as_of"}
    assert all(isinstance(v, int) for v in ledger.values())
    assert all(isinstance(v, int) for v in body["blocked_by_reason"].values())
    # The only free-form strings that reach the operator are the closed
    # reason vocabulary, the alert copy, and timestamps.
    assert set(body["blocked_by_reason"]) <= set(svc.BLOCK_REASONS)


def test_the_endpoint_answers_while_the_channel_is_off(
    client, admin_key, oa, monkeypatch
):
    # The rollback promise for ZALO_CHANNEL_ENABLED=false is about user
    # surfaces. Unmounting the instrument exactly when an incident starts
    # would remove the only view of what happened.
    monkeypatch.setattr(get_settings(), "zalo_channel_enabled", False)

    resp = _get(client, "/snapshot")

    assert resp.status_code == 200
    assert resp.json()["channel_enabled"] is False
