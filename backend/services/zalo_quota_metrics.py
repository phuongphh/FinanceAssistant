"""Blocked-send counters and quota reconciliation (Phase 5.0 #3.3).

The DoD this file serves: *"Log có cấu trúc + counter cho mỗi lần bị chặn
(theo ``reason``). Endpoint/health snippet đọc ``remain``/``total`` từ
quota API Zalo để đối chiếu đếm nội bộ với thực tế… số đếm nội bộ và
quota Zalo lệch >1 → cảnh báo."*

Two independent questions, answered side by side
------------------------------------------------
1. *Are we blocking sends, and why?* — read off the analytics events the
   notifier emits at the moment of the block, grouped by ``reason``.
2. *Does our accounting match Zalo's?* — compare what we believe we sent
   against what Zalo says the OA has left.

They are kept separate on purpose. (1) is always available and always
trustworthy. (2) depends on an endpoint we do not control and a baseline
an operator has to capture, so it can be *unavailable* — and an
unavailable reconciliation must never be reported as a passing one.

Why reconciliation is delta-vs-delta, not absolute
--------------------------------------------------
Zalo's ``remain`` counts every message the OA sent, including any sent
from the Zalo OA web console by a human, and it resets on a cycle we do
not observe. Our counters start whenever this feature shipped. The two
absolute numbers were never going to agree, so comparing them would
produce a permanent alarm.

What *is* comparable is movement over the same interval: between two
observations, the number Zalo says was consumed should match the number
we say we delivered. Hence :func:`reconcile` takes a baseline the
operator captured earlier and compares deltas. Without one it reports
``need_baseline`` rather than guessing — see the runbook procedure.

Contract with the layer rules
-----------------------------
Read-only aggregations. No ``db.commit()``, no env reads, no transport:
the quota figure is fetched by the caller (the admin router) and passed
in, so this module stays testable without a network and a Zalo outage
degrades the snapshot instead of failing it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import EventType
from backend.models.event import Event
from backend.models.zalo_message_window import FREE_MESSAGE_QUOTA, ZaloMessageWindow
from backend.services.zalo_window_service import (
    BLOCK_REASONS,
    REASON_NOT_CONFIGURED,
    REASON_QUOTA_EXHAUSTED,
)

logger = logging.getLogger(__name__)

# Event names, taken from the enum the notifier emits rather than
# re-typed, so a rename cannot silently empty this dashboard.
EVENT_SEND_BLOCKED = EventType.ZALO_SEND_BLOCKED
EVENT_SEND_DELIVERED = EventType.ZALO_SEND_DELIVERED

# How far back the snapshot looks when the caller doesn't say.
DEFAULT_LOOKBACK_HOURS = 24

#: Drift the DoD tolerates before it becomes an alert. One is expected,
#: not exceptional: the reservation commits before the send, so a crash
#: in that gap legitimately leaves our count one ahead of Zalo's — the
#: direction :mod:`backend.services.zalo_window_service` deliberately
#: errs in. Two or more is a real accounting divergence.
ALERT_QUOTA_DRIFT_TOLERANCE = 1

#: Share of send attempts blocked for ``quota_exhausted`` above which the
#: eight-message allowance is the binding constraint on the product, not
#: a safety net. Worth an operator's attention, not a page.
ALERT_QUOTA_EXHAUSTED_SHARE_CEILING = 0.10

#: Below this many attempts a share is noise — three blocks out of five
#: sends on a quiet morning is not a trend.
MIN_ATTEMPTS_FOR_RATE_ALERT = 20

# Reconciliation outcomes. Stable strings: the runbook names them.
RECONCILE_OK = "ok"
RECONCILE_NEED_BASELINE = "need_baseline"
RECONCILE_QUOTA_UNAVAILABLE = "quota_unavailable"
RECONCILE_BASELINE_STALE = "baseline_stale"

__all__ = [
    "ALERT_QUOTA_DRIFT_TOLERANCE",
    "ALERT_QUOTA_EXHAUSTED_SHARE_CEILING",
    "DEFAULT_LOOKBACK_HOURS",
    "EVENT_SEND_BLOCKED",
    "EVENT_SEND_DELIVERED",
    "MIN_ATTEMPTS_FOR_RATE_ALERT",
    "RECONCILE_BASELINE_STALE",
    "RECONCILE_NEED_BASELINE",
    "RECONCILE_OK",
    "RECONCILE_QUOTA_UNAVAILABLE",
    "blocked_counts",
    "delivered_count",
    "evaluate_alerts",
    "parse_baseline_at",
    "reconcile",
    "snapshot",
    "window_ledger",
]


def _default_since() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=DEFAULT_LOOKBACK_HOURS)


async def blocked_counts(
    db: AsyncSession, *, since: datetime | None = None
) -> dict[str, int]:
    """How many sends were blocked, per ``reason``.

    Every member of ``BLOCK_REASONS`` appears in the result even at zero,
    so a dashboard row doesn't vanish when the problem it tracks goes
    away — an absent row and a zero row look the same to a human and mean
    opposite things.

    Reasons *outside* the vocabulary are returned as they were recorded
    rather than folded into an "other" bucket. If one shows up, some call
    site invented a label, and :func:`evaluate_alerts` says so.
    """
    since = since or _default_since()

    stmt = (
        select(
            Event.properties["reason"].astext.label("reason"),
            func.count().label("total"),
        )
        .where(
            Event.event_type == EVENT_SEND_BLOCKED,
            Event.timestamp >= since,
        )
        .group_by(Event.properties["reason"].astext)
    )

    counts: dict[str, int] = {reason: 0 for reason in BLOCK_REASONS}
    for row in (await db.execute(stmt)).all():
        counts[row.reason or "unknown"] = int(row.total)
    return counts


async def delivered_count(
    db: AsyncSession, *, since: datetime | None = None
) -> int:
    """How many sends actually reached the OA in the window."""
    since = since or _default_since()

    stmt = (
        select(func.count())
        .select_from(Event)
        .where(
            Event.event_type == EVENT_SEND_DELIVERED,
            Event.timestamp >= since,
        )
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def window_ledger(
    db: AsyncSession, *, now: datetime | None = None
) -> dict:
    """Current state of the local 48h-window ledger, in one query.

    ``now`` is a parameter rather than a call to the clock so a test can
    place a window on either side of the boundary without sleeping, and
    so the whole snapshot is evaluated against a single instant instead
    of drifting between aggregates.
    """
    now = now or datetime.now(timezone.utc)

    is_open = ZaloMessageWindow.window_expires_at > now
    open_flag = case((is_open, 1), else_=0)
    exhausted_flag = case(
        (
            is_open & (ZaloMessageWindow.free_msg_count >= FREE_MESSAGE_QUOTA),
            1,
        ),
        else_=0,
    )

    stmt = select(
        func.count().label("tracked_senders"),
        func.coalesce(func.sum(open_flag), 0).label("open_windows"),
        func.coalesce(func.sum(exhausted_flag), 0).label("exhausted_windows"),
        func.coalesce(
            func.sum(
                case(
                    (is_open, ZaloMessageWindow.free_msg_count),
                    else_=0,
                ).cast(Integer)
            ),
            0,
        ).label("slots_used_open"),
    )
    row = (await db.execute(stmt)).one()

    open_windows = int(row.open_windows or 0)
    slots_used = int(row.slots_used_open or 0)
    return {
        "as_of": now.isoformat(),
        "tracked_senders": int(row.tracked_senders or 0),
        "open_windows": open_windows,
        "exhausted_windows": int(row.exhausted_windows or 0),
        "slots_used_open": slots_used,
        "slots_available_open": max(
            0, open_windows * FREE_MESSAGE_QUOTA - slots_used
        ),
        "quota_per_window": FREE_MESSAGE_QUOTA,
    }


def reconcile(
    *,
    delivered_since_baseline: int,
    quota_remain: int | None,
    baseline_remain: int | None,
) -> dict:
    """Compare our delivery count against Zalo's own consumption.

    Pure and stateless — every input is a number the caller obtained, so
    this is the part of #3.3 that can be exhaustively unit-tested without
    a database or a network.

    ``quota_remain is None`` means the quota call failed, and that is
    reported as :data:`RECONCILE_QUOTA_UNAVAILABLE`, never as a drift of
    zero and never as a drift equal to everything we sent. An outage that
    fabricates a drift alarm teaches operators to close drift alarms
    without reading them.

    A ``quota_remain`` *above* the baseline means Zalo topped the
    allowance up between the two observations, so the interval spans a
    reset and the deltas describe different things. That is
    :data:`RECONCILE_BASELINE_STALE`: the operator re-baselines, nobody
    gets paged.
    """
    if quota_remain is None:
        return {
            "comparable": False,
            "status": RECONCILE_QUOTA_UNAVAILABLE,
            "internal_delta": delivered_since_baseline,
            "zalo_delta": None,
            "drift": None,
        }
    if baseline_remain is None:
        return {
            "comparable": False,
            "status": RECONCILE_NEED_BASELINE,
            "internal_delta": delivered_since_baseline,
            "zalo_delta": None,
            "drift": None,
        }

    zalo_delta = baseline_remain - quota_remain
    if zalo_delta < 0:
        return {
            "comparable": False,
            "status": RECONCILE_BASELINE_STALE,
            "internal_delta": delivered_since_baseline,
            "zalo_delta": zalo_delta,
            "drift": None,
        }

    return {
        "comparable": True,
        "status": RECONCILE_OK,
        "internal_delta": delivered_since_baseline,
        "zalo_delta": zalo_delta,
        "drift": abs(delivered_since_baseline - zalo_delta),
    }


async def snapshot(
    db: AsyncSession,
    *,
    quota: dict[str, int] | None = None,
    baseline: dict | None = None,
    since: datetime | None = None,
    now: datetime | None = None,
) -> dict:
    """Everything the #3.3 endpoint reports, in three queries.

    ``quota`` is whatever :meth:`ZaloOAClient.get_message_quota` returned
    — including ``None`` for "could not be read". ``baseline`` is the
    operator-captured ``{"remain": int, "captured_at": <ISO8601>}`` from
    the runbook procedure; without it the counters still render and only
    the reconciliation degrades.
    """
    since = since or _default_since()

    blocked = await blocked_counts(db, since=since)
    delivered = await delivered_count(db, since=since)
    ledger = await window_ledger(db, now=now)

    baseline_remain = None
    baseline_at = None
    delivered_since_baseline = delivered
    if baseline:
        baseline_remain = baseline.get("remain")
        baseline_at = parse_baseline_at(baseline.get("captured_at"))
        if baseline_at is not None:
            # Counted over the baseline's own interval, not the snapshot
            # window — otherwise a 24h lookback compared against a
            # week-old baseline invents drift out of the mismatch.
            delivered_since_baseline = await delivered_count(db, since=baseline_at)
        else:
            baseline_remain = None

    blocked_total = sum(blocked.values())
    attempts = blocked_total + delivered

    return {
        "since": since.isoformat(),
        "attempts": attempts,
        "delivered": delivered,
        "blocked_total": blocked_total,
        "blocked_by_reason": blocked,
        "window_ledger": ledger,
        "zalo_quota": quota,
        "baseline": {
            "remain": baseline_remain,
            "captured_at": baseline_at.isoformat() if baseline_at else None,
            "delivered_since": delivered_since_baseline,
        },
        "reconciliation": reconcile(
            delivered_since_baseline=delivered_since_baseline,
            quota_remain=(quota or {}).get("remain") if quota else None,
            baseline_remain=baseline_remain,
        ),
    }


def evaluate_alerts(snap: dict) -> list[dict]:
    """Turn a snapshot into the rows an operator should act on.

    Same shape as :func:`backend.services.intent_metrics.evaluate_alerts`
    — ``{"code", "message"}`` — so the admin surface renders both without
    a special case.
    """
    alerts: list[dict] = []

    recon = snap.get("reconciliation") or {}
    drift = recon.get("drift")
    if recon.get("comparable") and drift is not None:
        if drift > ALERT_QUOTA_DRIFT_TOLERANCE:
            alerts.append({
                "code": "zalo_quota_drift",
                "message": (
                    f"Đếm nội bộ {recon['internal_delta']} tin, Zalo trừ "
                    f"{recon['zalo_delta']} tin — lệch {drift} "
                    f"(ngưỡng {ALERT_QUOTA_DRIFT_TOLERANCE}). "
                    "Xem docs/conventions/zalo-operations.md §Quota drift."
                ),
            })
    elif recon.get("status") == RECONCILE_QUOTA_UNAVAILABLE:
        alerts.append({
            "code": "zalo_quota_unavailable",
            "message": (
                "Không đọc được quota từ Zalo — số liệu đối chiếu tạm "
                "thời không dùng được (đếm nội bộ vẫn đúng)."
            ),
        })
    elif recon.get("status") == RECONCILE_BASELINE_STALE:
        alerts.append({
            "code": "zalo_quota_baseline_stale",
            "message": (
                "Quota Zalo tăng so với mốc đã lưu — nhiều khả năng đã "
                "sang chu kỳ mới. Chụp lại mốc theo runbook."
            ),
        })
    elif recon.get("status") == RECONCILE_NEED_BASELINE:
        alerts.append({
            "code": "zalo_quota_need_baseline",
            "message": (
                "Chưa có mốc quota để đối chiếu. Chạy bước 'chụp mốc' "
                "trong runbook trước khi tin vào con số lệch."
            ),
        })

    blocked = snap.get("blocked_by_reason") or {}
    attempts = int(snap.get("attempts") or 0)

    exhausted = int(blocked.get(REASON_QUOTA_EXHAUSTED, 0))
    if attempts >= MIN_ATTEMPTS_FOR_RATE_ALERT:
        share = exhausted / attempts
        if share > ALERT_QUOTA_EXHAUSTED_SHARE_CEILING:
            alerts.append({
                "code": "zalo_quota_exhausted_high",
                "message": (
                    f"{share * 100:.1f}% lượt gửi bị chặn vì hết 8 tin/cửa "
                    f"sổ (ngưỡng {ALERT_QUOTA_EXHAUSTED_SHARE_CEILING * 100:.0f}%) "
                    "— trần Zalo đang là ràng buộc thật, không phải lưới an toàn."
                ),
            })

    if int(blocked.get(REASON_NOT_CONFIGURED, 0)) > 0:
        alerts.append({
            "code": "zalo_not_configured",
            "message": (
                f"{blocked[REASON_NOT_CONFIGURED]} lượt gửi bị chặn vì OA "
                "chưa có credential dùng được trên server này."
            ),
        })

    unknown = sorted(set(blocked) - set(BLOCK_REASONS))
    if unknown:
        alerts.append({
            "code": "zalo_block_reason_unknown",
            "message": (
                "Có lý do chặn ngoài từ vựng đã chốt: "
                f"{', '.join(unknown)} — thêm vào BLOCK_REASONS hoặc sửa "
                "call site, nếu không dashboard sẽ bỏ sót."
            ),
        })

    return alerts


def parse_baseline_at(raw: object) -> datetime | None:
    """Parse the operator-supplied baseline timestamp, tolerantly.

    Returns ``None`` for anything unparseable, which downgrades the
    reconciliation to ``need_baseline``. A half-understood baseline is
    worse than none: it would silently compare our count over one
    interval against Zalo's over another.

    Public so the admin router can reject a malformed timestamp with a
    400 the operator can read, instead of silently serving a snapshot
    whose reconciliation quietly degraded. One parser, two callers — a
    second implementation at the edge would eventually disagree with this
    one about what a valid baseline is.
    """
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str):
        text = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            logger.warning("zalo.quota.baseline_unparseable")
            return None
    else:
        return None

    if parsed.tzinfo is None:
        # Naive input is read as UTC — every timestamp this system
        # stores is UTC, and guessing the server's local zone here would
        # shift the comparison interval by 7 hours in Asia/Ho_Chi_Minh.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
