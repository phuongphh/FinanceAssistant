"""Blocked-send counters and quota reconciliation (Phase 5.0 #3.3).

The DoD sentence under test: *"Log có cấu trúc + counter cho mỗi lần bị
chặn (theo ``reason``)… số đếm nội bộ và quota Zalo lệch >1 → cảnh báo."*

Three separable claims, and the failure mode each one guards:

* **every block is counted, under a name the runbook knows** — a reason
  that never appears in ``BLOCK_REASONS`` lands in a bucket no dashboard
  reads, so the counters look healthy while sends disappear. Hence both
  the "zeros are always present" test and the deliberately loud
  ``zalo_block_reason_unknown`` alert.
* **a reconciliation that can't be computed says so** — the one thing
  that must never happen is an unavailable quota read being reported as
  a drift of zero (silently green) or as a drift of everything we sent
  (an alarm operators learn to dismiss). Both directions are asserted.
* **drift compares movement to movement** — the snapshot counts our
  deliveries over the *baseline's* interval, not the lookback window, or
  a 24h snapshot against a week-old baseline invents drift out of the
  mismatch alone.

No database: every aggregate here is read-only SQL, answered by
``FakeMetricsSession`` in ``conftest.py``, which routes on the compiled
statement so a query that changes shape fails loudly instead of quietly
returning the previous query's numbers. :func:`reconcile`,
:func:`parse_baseline_at` and :func:`evaluate_alerts` are pure and are
tested directly.

The last section is a contract test rather than a unit test: it drives
the real notifier and asserts the events it *writes* are the events this
module *reads*. The two halves of #3.3 are only useful together, and they
live in different layers, so nothing else would catch them drifting.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from backend import analytics
from backend.adapters import zalo_window_notifier as notifier_mod
from backend.adapters.zalo_window_notifier import WindowedZaloNotifier
from backend.models.zalo_message_window import FREE_MESSAGE_QUOTA
from backend.services import zalo_quota_metrics as mod
from backend.services import zalo_window_service as svc

from tests.test_phase_5_0.conftest import FakeMetricsSession

SENDER = "zalo-sender-should-never-be-logged"


def _at(hours_ago: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


# ---------------------------------------------------------------------------
# reconcile — pure, and the part an operator's judgement rests on
# ---------------------------------------------------------------------------


def test_matching_movements_reconcile_to_zero_drift():
    out = mod.reconcile(
        delivered_since_baseline=12, quota_remain=88, baseline_remain=100
    )

    assert out["comparable"] is True
    assert out["status"] == mod.RECONCILE_OK
    assert out["internal_delta"] == 12
    assert out["zalo_delta"] == 12
    assert out["drift"] == 0


def test_a_quiet_interval_is_a_valid_reconciliation_not_a_missing_one():
    # Nothing sent, nothing consumed. This has to come back ``ok`` with
    # drift 0 — reporting "no data" for a quiet night would train the
    # operator to ignore the same wording when it means a broken read.
    out = mod.reconcile(
        delivered_since_baseline=0, quota_remain=100, baseline_remain=100
    )

    assert (out["status"], out["drift"], out["comparable"]) == (
        mod.RECONCILE_OK,
        0,
        True,
    )


@pytest.mark.parametrize(
    ("delivered", "remain", "expected_drift"),
    [
        (12, 95, 7),  # we think we sent more than Zalo charged us for
        (3, 88, 9),  # Zalo charged more than we think we sent
    ],
)
def test_drift_is_the_absolute_disagreement_in_either_direction(
    delivered, remain, expected_drift
):
    out = mod.reconcile(
        delivered_since_baseline=delivered, quota_remain=remain, baseline_remain=100
    )

    assert out["drift"] == expected_drift
    assert out["status"] == mod.RECONCILE_OK


def test_an_unreadable_quota_is_reported_as_unavailable_not_as_zero_drift():
    out = mod.reconcile(
        delivered_since_baseline=12, quota_remain=None, baseline_remain=100
    )

    assert out["comparable"] is False
    assert out["status"] == mod.RECONCILE_QUOTA_UNAVAILABLE
    # Neither 0 (silently green) nor 12 (a fabricated alarm).
    assert out["drift"] is None
    assert out["zalo_delta"] is None
    # What we *do* know is still reported.
    assert out["internal_delta"] == 12


def test_a_failed_quota_read_outranks_a_missing_baseline():
    # Both are unknown; the quota read is the one the operator can't fix
    # by following the runbook, so it is the one worth naming.
    out = mod.reconcile(
        delivered_since_baseline=0, quota_remain=None, baseline_remain=None
    )

    assert out["status"] == mod.RECONCILE_QUOTA_UNAVAILABLE


def test_without_a_baseline_nothing_is_compared():
    out = mod.reconcile(
        delivered_since_baseline=12, quota_remain=88, baseline_remain=None
    )

    assert out["comparable"] is False
    assert out["status"] == mod.RECONCILE_NEED_BASELINE
    assert out["drift"] is None


def test_a_quota_that_went_up_means_the_period_rolled_over():
    # Zalo topped the allowance back up between the two observations, so
    # the deltas describe different things. Re-baseline; don't page.
    out = mod.reconcile(
        delivered_since_baseline=12, quota_remain=120, baseline_remain=100
    )

    assert out["status"] == mod.RECONCILE_BASELINE_STALE
    assert out["comparable"] is False
    assert out["drift"] is None
    # The negative delta is echoed so the runbook reader can see *how*
    # stale the baseline was without re-deriving it.
    assert out["zalo_delta"] == -20


# ---------------------------------------------------------------------------
# parse_baseline_at — the operator types this by hand
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-08-01T10:00:00Z", datetime(2026, 8, 1, 10, tzinfo=timezone.utc)),
        ("2026-08-01T10:00:00+00:00", datetime(2026, 8, 1, 10, tzinfo=timezone.utc)),
        # Naive input is UTC, never the server's local zone: reading this
        # as Asia/Ho_Chi_Minh would shift the comparison interval by 7h.
        ("2026-08-01T10:00:00", datetime(2026, 8, 1, 10, tzinfo=timezone.utc)),
        ("  2026-08-01T10:00:00Z  ", datetime(2026, 8, 1, 10, tzinfo=timezone.utc)),
    ],
)
def test_baseline_timestamps_are_parsed_as_utc(raw, expected):
    assert mod.parse_baseline_at(raw) == expected


def test_an_offset_timestamp_keeps_its_instant():
    parsed = mod.parse_baseline_at("2026-08-01T17:00:00+07:00")

    assert parsed == datetime(2026, 8, 1, 10, tzinfo=timezone.utc)


def test_a_datetime_passes_through_and_a_naive_one_gains_utc():
    aware = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)

    assert mod.parse_baseline_at(aware) is aware
    assert mod.parse_baseline_at(datetime(2026, 8, 1, 10)) == aware


@pytest.mark.parametrize("raw", ["not-a-timestamp", "", "2026-13-99", 1754092800, None])
def test_an_unparseable_baseline_is_none_rather_than_a_guess(raw):
    # ``None`` degrades the reconciliation to ``need_baseline``. A
    # half-understood baseline would compare our count over one interval
    # against Zalo's over another and call the difference drift.
    assert mod.parse_baseline_at(raw) is None


def test_an_unparseable_baseline_leaves_a_trace(caplog):
    with caplog.at_level("WARNING", logger="backend.services.zalo_quota_metrics"):
        mod.parse_baseline_at("nonsense")

    assert "zalo.quota.baseline_unparseable" in caplog.text


# ---------------------------------------------------------------------------
# blocked_counts / delivered_count / window_ledger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_block_reason_has_a_row_even_at_zero():
    # An absent row and a zero row look identical to a human reading a
    # dashboard, and they mean opposite things ("never happens" vs. "the
    # counter went away"). Seeding the vocabulary removes the ambiguity.
    counts = await mod.blocked_counts(FakeMetricsSession(), since=_at(1))

    assert set(counts) == set(svc.BLOCK_REASONS)
    assert set(counts.values()) == {0}


@pytest.mark.asyncio
async def test_recorded_reasons_overwrite_their_zero_row():
    db = FakeMetricsSession(blocked={svc.REASON_QUOTA_EXHAUSTED: 4})

    counts = await mod.blocked_counts(db, since=_at(1))

    assert counts[svc.REASON_QUOTA_EXHAUSTED] == 4
    assert counts[svc.REASON_NO_WINDOW] == 0


@pytest.mark.asyncio
async def test_a_reason_outside_the_vocabulary_survives_verbatim():
    # Not folded into an "other" bucket: the whole point is that
    # ``evaluate_alerts`` can name the offending label so someone can go
    # and fix the call site that invented it.
    db = FakeMetricsSession(blocked={"invented_by_some_call_site": 2})

    counts = await mod.blocked_counts(db, since=_at(1))

    assert counts["invented_by_some_call_site"] == 2


@pytest.mark.asyncio
async def test_a_null_reason_is_counted_as_unknown():
    db = FakeMetricsSession(blocked={None: 3})

    counts = await mod.blocked_counts(db, since=_at(1))

    assert counts["unknown"] == 3


@pytest.mark.asyncio
async def test_delivered_count_reads_the_scalar_and_treats_empty_as_zero():
    assert await mod.delivered_count(FakeMetricsSession(delivered=9), since=_at(1)) == 9
    assert (
        await mod.delivered_count(FakeMetricsSession(delivered=None), since=_at(1)) == 0
    )


@pytest.mark.asyncio
async def test_delivered_count_asks_for_the_interval_it_was_given():
    db = FakeMetricsSession(delivered=1)
    since = _at(6)

    await mod.delivered_count(db, since=since)

    assert db.delivered_since == [since]


@pytest.mark.asyncio
async def test_the_window_ledger_reports_capacity_not_just_usage():
    db = FakeMetricsSession(
        ledger={
            "tracked_senders": 10,
            "open_windows": 3,
            "exhausted_windows": 1,
            "slots_used_open": 11,
        }
    )
    now = _at(0)

    ledger = await mod.window_ledger(db, now=now)

    assert ledger["quota_per_window"] == FREE_MESSAGE_QUOTA
    assert ledger["slots_used_open"] == 11
    assert ledger["slots_available_open"] == 3 * FREE_MESSAGE_QUOTA - 11
    assert ledger["as_of"] == now.isoformat()


@pytest.mark.asyncio
async def test_available_slots_never_go_negative():
    # Over-counting by one is the direction the reservation protocol
    # deliberately errs in (see the notifier's module docstring), so the
    # arithmetic has to survive it rather than render "-1 slots left".
    db = FakeMetricsSession(
        ledger={"open_windows": 1, "slots_used_open": FREE_MESSAGE_QUOTA + 1}
    )

    ledger = await mod.window_ledger(db, now=_at(0))

    assert ledger["slots_available_open"] == 0


# ---------------------------------------------------------------------------
# snapshot — the three aggregates plus the reconciliation, assembled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attempts_is_deliveries_plus_every_kind_of_block():
    db = FakeMetricsSession(
        blocked={svc.REASON_QUOTA_EXHAUSTED: 2, svc.REASON_SEND_FAILED: 1},
        delivered=7,
    )

    snap = await mod.snapshot(db, since=_at(24), now=_at(0))

    assert snap["delivered"] == 7
    assert snap["blocked_total"] == 3
    assert snap["attempts"] == 10


@pytest.mark.asyncio
async def test_without_a_baseline_the_counters_still_render():
    # The two halves of the snapshot are independent on purpose: a
    # missing baseline degrades the reconciliation and nothing else.
    db = FakeMetricsSession(blocked={svc.REASON_NO_WINDOW: 5}, delivered=2)

    snap = await mod.snapshot(db, quota={"remain": 40, "total": 100}, since=_at(24))

    assert snap["blocked_by_reason"][svc.REASON_NO_WINDOW] == 5
    assert snap["zalo_quota"] == {"remain": 40, "total": 100}
    assert snap["reconciliation"]["status"] == mod.RECONCILE_NEED_BASELINE
    assert db.delivered_since != []


@pytest.mark.asyncio
async def test_a_baseline_is_compared_over_its_own_interval_not_the_lookback():
    # The bug this pins: counting deliveries over the 24h lookback while
    # Zalo's delta covers a week-old baseline would report the mismatch
    # between the two intervals as drift.
    lookback_since = _at(24)
    baseline_at = _at(168)
    db = FakeMetricsSession(delivered=[4, 30])  # lookback first, baseline second

    snap = await mod.snapshot(
        db,
        quota={"remain": 70},
        baseline={"remain": 100, "captured_at": baseline_at},
        since=lookback_since,
    )

    assert db.delivered_since == [lookback_since, baseline_at]
    assert snap["delivered"] == 4  # the window the operator asked about
    assert snap["baseline"]["delivered_since"] == 30  # what the drift uses
    assert snap["reconciliation"]["internal_delta"] == 30
    assert snap["reconciliation"]["zalo_delta"] == 30
    assert snap["reconciliation"]["drift"] == 0


@pytest.mark.asyncio
async def test_a_baseline_with_an_unreadable_timestamp_is_dropped_entirely():
    # Not partially honoured: without a usable interval the ``remain``
    # figure is meaningless, so it goes too and the status says so.
    db = FakeMetricsSession(delivered=3)

    snap = await mod.snapshot(
        db,
        quota={"remain": 70},
        baseline={"remain": 100, "captured_at": "sometime yesterday"},
        since=_at(24),
    )

    assert snap["baseline"]["remain"] is None
    assert snap["baseline"]["captured_at"] is None
    assert snap["reconciliation"]["status"] == mod.RECONCILE_NEED_BASELINE
    # Only the lookback query ran — no second count over a parsed-to-None
    # interval, which would have silently meant "since the epoch".
    assert len(db.delivered_since) == 1


@pytest.mark.asyncio
async def test_a_quota_outage_degrades_the_snapshot_instead_of_failing_it():
    db = FakeMetricsSession(blocked={svc.REASON_WINDOW_CLOSED: 1}, delivered=[2, 2])

    snap = await mod.snapshot(
        db,
        quota=None,
        baseline={"remain": 100, "captured_at": _at(24)},
        since=_at(24),
    )

    assert snap["zalo_quota"] is None
    assert snap["reconciliation"]["status"] == mod.RECONCILE_QUOTA_UNAVAILABLE
    assert snap["blocked_by_reason"][svc.REASON_WINDOW_CLOSED] == 1


@pytest.mark.asyncio
async def test_the_snapshot_never_writes():
    db = FakeMetricsSession(delivered=1)

    await mod.snapshot(db, since=_at(24))

    assert db.commits == 0


# ---------------------------------------------------------------------------
# evaluate_alerts
# ---------------------------------------------------------------------------


def _snap(*, blocked=None, delivered=0, reconciliation=None) -> dict:
    """A snapshot-shaped dict with only the fields the alerts read."""
    counts = {reason: 0 for reason in svc.BLOCK_REASONS}
    counts.update(blocked or {})
    return {
        "attempts": sum(counts.values()) + delivered,
        "delivered": delivered,
        "blocked_total": sum(counts.values()),
        "blocked_by_reason": counts,
        "reconciliation": reconciliation
        or {"comparable": False, "status": mod.RECONCILE_NEED_BASELINE, "drift": None},
    }


def _codes(snap: dict) -> list[str]:
    return [alert["code"] for alert in mod.evaluate_alerts(snap)]


def test_a_healthy_snapshot_raises_nothing():
    snap = _snap(
        delivered=50,
        reconciliation={
            "comparable": True,
            "status": mod.RECONCILE_OK,
            "internal_delta": 50,
            "zalo_delta": 50,
            "drift": 0,
        },
    )

    assert mod.evaluate_alerts(snap) == []


@pytest.mark.parametrize(
    ("drift", "expected"),
    [
        (mod.ALERT_QUOTA_DRIFT_TOLERANCE, False),
        (mod.ALERT_QUOTA_DRIFT_TOLERANCE + 1, True),
    ],
)
def test_drift_alerts_only_above_the_tolerance(drift, expected):
    # Drift of exactly 1 is the crash-between-reserve-and-send case the
    # protocol accepts by design; alerting on it would make the alert
    # routine, and a routine alert is an ignored alert.
    snap = _snap(
        delivered=10,
        reconciliation={
            "comparable": True,
            "status": mod.RECONCILE_OK,
            "internal_delta": 10,
            "zalo_delta": 10 - drift,
            "drift": drift,
        },
    )

    assert ("zalo_quota_drift" in _codes(snap)) is expected


def test_the_drift_alert_points_at_the_runbook():
    snap = _snap(
        reconciliation={
            "comparable": True,
            "status": mod.RECONCILE_OK,
            "internal_delta": 10,
            "zalo_delta": 4,
            "drift": 6,
        },
    )

    (alert,) = mod.evaluate_alerts(snap)
    assert alert["code"] == "zalo_quota_drift"
    assert "zalo-operations.md" in alert["message"]


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (mod.RECONCILE_QUOTA_UNAVAILABLE, "zalo_quota_unavailable"),
        (mod.RECONCILE_BASELINE_STALE, "zalo_quota_baseline_stale"),
        (mod.RECONCILE_NEED_BASELINE, "zalo_quota_need_baseline"),
    ],
)
def test_every_non_comparable_status_names_itself(status, code):
    snap = _snap(reconciliation={"comparable": False, "status": status, "drift": None})

    assert _codes(snap) == [code]


def test_a_non_comparable_snapshot_raises_exactly_one_reconciliation_alert():
    # The statuses are mutually exclusive; emitting both "can't read the
    # quota" and "no baseline" for one snapshot would send the operator
    # to capture a baseline that still won't reconcile.
    snap = _snap(
        reconciliation={
            "comparable": False,
            "status": mod.RECONCILE_QUOTA_UNAVAILABLE,
            "drift": None,
        }
    )

    assert _codes(snap) == ["zalo_quota_unavailable"]


def test_the_eight_message_ceiling_is_flagged_when_it_binds():
    # 8 refusals in 50 attempts is 16%, past the 10% ceiling: the 8-message
    # cap is turning away real replies often enough to be worth a look.
    snap = _snap(blocked={svc.REASON_QUOTA_EXHAUSTED: 8}, delivered=42)

    assert "zalo_quota_exhausted_high" in _codes(snap)


def test_a_share_at_the_ceiling_is_not_yet_an_alert():
    # 10% of 50 attempts is exactly the ceiling; the comparison is
    # strictly greater-than so the documented threshold means what it says.
    exhausted = 5
    delivered = 45
    snap = _snap(blocked={svc.REASON_QUOTA_EXHAUSTED: exhausted}, delivered=delivered)
    snap["attempts"] = 50

    assert exhausted / 50 == mod.ALERT_QUOTA_EXHAUSTED_SHARE_CEILING
    assert "zalo_quota_exhausted_high" not in _codes(snap)


def test_a_small_sample_cannot_trigger_a_rate_alert():
    # Three blocks out of five sends on a quiet morning is not a trend.
    snap = _snap(blocked={svc.REASON_QUOTA_EXHAUSTED: 3}, delivered=2)

    assert snap["attempts"] < mod.MIN_ATTEMPTS_FOR_RATE_ALERT
    assert "zalo_quota_exhausted_high" not in _codes(snap)


def test_a_missing_credential_is_flagged_on_the_first_occurrence():
    # No rate threshold here on purpose: one block for ``not_configured``
    # means the server cannot talk to the OA at all, which is not a
    # gradient.
    snap = _snap(blocked={svc.REASON_NOT_CONFIGURED: 1})

    assert "zalo_not_configured" in _codes(snap)


def test_an_unknown_reason_is_named_so_the_call_site_can_be_found():
    snap = _snap(blocked={"zoinks": 1, "aardvark": 2})

    (alert,) = [a for a in mod.evaluate_alerts(snap) if a["code"] == "zalo_block_reason_unknown"]
    # Sorted, so the message is stable across runs and diffable.
    assert "aardvark, zoinks" in alert["message"]


def test_the_whole_closed_vocabulary_is_considered_known():
    snap = _snap(blocked={reason: 1 for reason in svc.BLOCK_REASONS})

    assert "zalo_block_reason_unknown" not in _codes(snap)


def test_alert_messages_are_vietnamese_and_carry_no_identifier():
    snap = _snap(
        blocked={svc.REASON_NOT_CONFIGURED: 1, svc.REASON_QUOTA_EXHAUSTED: 9},
        delivered=40,
        reconciliation={
            "comparable": True,
            "status": mod.RECONCILE_OK,
            "internal_delta": 40,
            "zalo_delta": 10,
            "drift": 30,
        },
    )

    alerts = mod.evaluate_alerts(snap)

    assert alerts, "this snapshot is supposed to be alarming"
    for alert in alerts:
        assert set(alert) == {"code", "message"}
        assert alert["message"].strip()
        assert SENDER not in alert["message"]


# ---------------------------------------------------------------------------
# Contract: the events this module reads are the events the notifier writes
# ---------------------------------------------------------------------------


class _FakeInner:
    """The transport half of the notifier, without a socket."""

    def __init__(self, *, configured: bool = True, result=None) -> None:
        self.is_configured = configured
        self._result = result
        self.sent: list[str] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)
        return self._result


@pytest.fixture()
def tracked(monkeypatch) -> list[tuple[str, dict]]:
    """Capture ``analytics.track`` instead of scheduling a DB write."""
    calls: list[tuple[str, dict]] = []

    def _track(event_type, user_id=None, properties=None):
        calls.append((event_type, dict(properties or {})))

    monkeypatch.setattr(analytics, "track", _track)
    return calls


def _notifier(store, inner) -> WindowedZaloNotifier:
    @contextlib.asynccontextmanager
    async def _open():
        yield store

    return WindowedZaloNotifier(inner, SENDER, session_factory=lambda: _open())


async def _block_reason(store, inner, tracked) -> str:
    await _notifier(store, inner).send_message(0, "Đã ghi 50k")
    blocked = [p for e, p in tracked if e == mod.EVENT_SEND_BLOCKED]
    assert len(blocked) == 1
    return blocked[0]["reason"]


@pytest.mark.asyncio
async def test_a_delivered_send_is_recorded_under_the_name_the_metrics_read(
    window_store, tracked
):
    await svc.record_inbound(window_store, zalo_user_id=SENDER)
    inner = _FakeInner(result={"ok": True, "channel": "zalo"})

    await _notifier(window_store, inner).send_message(0, "Đã ghi 50k")

    assert [e for e, _ in tracked] == [mod.EVENT_SEND_DELIVERED]
    assert mod.EVENT_SEND_DELIVERED == analytics.EventType.ZALO_SEND_DELIVERED


@pytest.mark.asyncio
async def test_every_block_reason_the_metrics_group_on_is_actually_emitted(
    window_store, tracked
):
    """The counter labels and the emitted reasons are the same five strings.

    Asserted by *producing* each one through the real notifier rather
    than by comparing two lists of constants — a vocabulary that matches
    on paper and is never emitted counts nothing.
    """
    seen = set()

    # not_configured — no usable credential on this server.
    seen.add(await _block_reason(window_store, _FakeInner(configured=False), tracked))
    tracked.clear()

    # no_window — this sender has never messaged us.
    seen.add(await _block_reason(window_store, _FakeInner(), tracked))
    tracked.clear()

    # window_closed — a window exists but the 48h elapsed.
    await svc.record_inbound(window_store, zalo_user_id=SENDER)
    window_store.rows[SENDER].window_expires_at = _at(1)
    seen.add(await _block_reason(window_store, _FakeInner(), tracked))
    tracked.clear()

    # quota_exhausted — all eight consulting messages spent.
    await svc.record_inbound(window_store, zalo_user_id=SENDER)
    window_store.rows[SENDER].free_msg_count = FREE_MESSAGE_QUOTA
    seen.add(await _block_reason(window_store, _FakeInner(), tracked))
    tracked.clear()

    # send_failed — transport declined after its own retries.
    await svc.record_inbound(window_store, zalo_user_id=SENDER)
    seen.add(await _block_reason(window_store, _FakeInner(result=None), tracked))

    assert seen == set(svc.BLOCK_REASONS)


@pytest.mark.asyncio
async def test_the_blocked_event_carries_no_recipient_and_no_message_text(
    window_store, tracked
):
    # The masked sender lives in the log line next to this event; the
    # events table is read only in aggregate, and one that accumulates
    # recipient ids is a PII liability nobody asked for.
    secret = "chuyển 5 triệu cho chị Lan"

    await _notifier(window_store, _FakeInner()).send_message(0, secret)

    (event, props) = tracked[0]
    assert event == mod.EVENT_SEND_BLOCKED == analytics.EventType.ZALO_SEND_BLOCKED
    assert set(props) == {"channel", "reason", "kind", "used", "remaining"}
    blob = repr(props)
    assert SENDER not in blob
    assert secret not in blob
    assert "chị Lan" not in blob


@pytest.mark.asyncio
async def test_the_reason_property_is_the_key_the_counters_group_on(
    window_store, tracked
):
    # ``blocked_counts`` groups on ``properties['reason']``; if the
    # notifier ever renamed the property the dashboard would report all
    # zeros while sends were being refused.
    await _notifier(window_store, _FakeInner()).send_message(0, "xin chào")

    (_, props) = tracked[0]
    assert props["reason"] in svc.BLOCK_REASONS
    assert props["channel"] == notifier_mod.WindowedZaloNotifier.channel
