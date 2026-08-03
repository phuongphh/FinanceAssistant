"""Operator view of the Zalo send ledger (Phase 5.0 #3.3).

The half of the DoD that isn't a log line: *"Endpoint/health snippet đọc
``remain``/``total`` từ quota API Zalo để đối chiếu đếm nội bộ với thực
tế… lệch >1 → cảnh báo."*

Two endpoints, because reconciliation needs two observations
------------------------------------------------------------
``GET /baseline`` reads Zalo's counter *now* and hands it back. The
operator saves it. ``GET /snapshot?baseline_remain=…&baseline_at=…``
reads it again later and compares the two movements: what Zalo consumed
between the observations against what we believe we delivered in the same
interval. The full reasoning for delta-vs-delta lives in
:mod:`backend.services.zalo_quota_metrics`.

The baseline is passed back in by the caller rather than stored. Storing
it would mean a table, a migration, and a second source of truth about
quota that can go stale silently — for a single-operator diagnostic
surface that reads out of a runbook, a query parameter is the honest
amount of machinery. The runbook has the two commands.

Why this is mounted whether or not the channel is enabled
---------------------------------------------------------
The rollback promise for ``ZALO_CHANNEL_ENABLED=false`` is about
user-facing behaviour: no webhook, no Zalo target, nothing sent. This
route sends nothing and touches no user surface — it is the instrument
you read *while deciding* to flip the flag, and again afterwards to
confirm the counters actually stopped. Unmounting it exactly when an
incident starts would remove the only view of what happened. It stays
behind ``INTERNAL_API_KEY`` and stays read-only.

Layer contract: this is an edge. It performs the one network call (the
quota read) and hands the result to the service as data, so the service
stays free of transport and testable without a socket. No writes, no
``commit()``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.zalo_oa import get_zalo_oa_client
from backend.config import get_settings
from backend.database import get_db
from backend.services import zalo_quota_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/zalo-quota", tags=["admin", "zalo"])

# Bounds on the lookback. One hour is the smallest interval that says
# anything; a week is where the events table stops being a cheap scan.
MIN_LOOKBACK_HOURS = 1
MAX_LOOKBACK_HOURS = 24 * 7


def _now() -> datetime:
    """UTC clock, in one place so tests can patch a single name."""
    return datetime.now(timezone.utc)


def _verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject calls without the configured admin key.

    Copied deliberately from
    :mod:`backend.routers.admin_agent_metrics` rather than shared: it is
    six lines, and every admin router in this repo carries its own so the
    auth for an endpoint is readable in the file that defines it.

    Empty key in settings = endpoint locked entirely (503), not "no auth
    required" — fail closed in case the operator forgot to set
    ``INTERNAL_API_KEY`` in prod.
    """
    expected = get_settings().internal_api_key
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="admin API not configured (INTERNAL_API_KEY unset)",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=403, detail="invalid X-API-Key")


async def _read_quota() -> dict[str, int] | None:
    """Ask Zalo how much allowance is left. Never raises.

    ``None`` means *unknown*. The client already collapses every failure
    to ``None``, but this catches anything it doesn't — a diagnostic
    endpoint that 500s during the incident it exists to explain is worse
    than one that reports "quota unavailable" and shows the internal
    counters, which remain correct regardless.
    """
    client = get_zalo_oa_client()
    if not client.is_configured:
        return None
    try:
        return await client.get_message_quota()
    except Exception:
        logger.exception("zalo.quota.read_failed")
        return None


@router.get("/baseline", dependencies=[Depends(_verify_api_key)])
async def capture_baseline() -> dict[str, Any]:
    """Step 1 of the reconciliation procedure: record where Zalo is now.

    Returns exactly the two values ``/snapshot`` wants back
    (``remain`` and ``captured_at``), so the runbook step is a copy-paste
    rather than a clock lookup the operator has to get right.

    ``remain: null`` means the read failed — save nothing and retry, since
    a baseline captured from an unknown is not a baseline.
    """
    quota = await _read_quota()
    return {
        "remain": (quota or {}).get("remain"),
        "total": (quota or {}).get("total"),
        "captured_at": _now().isoformat(),
        "channel_enabled": get_settings().zalo_channel_enabled,
    }


@router.get("/snapshot", dependencies=[Depends(_verify_api_key)])
async def quota_snapshot(
    hours: int = Query(
        default=zalo_quota_metrics.DEFAULT_LOOKBACK_HOURS,
        ge=MIN_LOOKBACK_HOURS,
        le=MAX_LOOKBACK_HOURS,
    ),
    baseline_remain: int | None = Query(default=None, ge=0),
    baseline_at: str | None = Query(default=None),
    read_quota: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Blocked-send counters, the local window ledger, and reconciliation.

    ``read_quota=false`` skips the network call and returns the internal
    half instantly. Worth having: the counters are the part an operator
    refreshes repeatedly during an incident, and each refresh should not
    cost a round trip to a third party that rate-limits us.

    Both baseline parameters are needed together. Supplying only one is
    rejected rather than half-honoured — a baseline remain without a
    timestamp would silently compare Zalo's movement over an unknown
    interval against ours over 24 hours.
    """
    if (baseline_remain is None) != (baseline_at is None):
        raise HTTPException(
            status_code=400,
            detail=(
                "baseline_remain and baseline_at must be supplied together "
                "(GET /admin/zalo-quota/baseline returns both)"
            ),
        )

    now = _now()
    baseline = None
    if baseline_remain is not None:
        # Validated here rather than left to degrade inside the service.
        # Both of these are operator typos, and a snapshot that silently
        # reports ``need_baseline`` after being handed a baseline reads as
        # a system fault instead of a fixable mistake.
        captured_at = zalo_quota_metrics.parse_baseline_at(baseline_at)
        if captured_at is None:
            raise HTTPException(
                status_code=400,
                detail="baseline_at must be an ISO-8601 timestamp",
            )
        if captured_at > now:
            raise HTTPException(
                status_code=400,
                detail="baseline_at is in the future",
            )
        baseline = {"remain": baseline_remain, "captured_at": captured_at}

    quota = await _read_quota() if read_quota else None

    snap = await zalo_quota_metrics.snapshot(
        db,
        quota=quota,
        baseline=baseline,
        since=now - timedelta(hours=hours),
        now=now,
    )
    snap["channel_enabled"] = get_settings().zalo_channel_enabled
    snap["quota_read_attempted"] = read_quota
    snap["alerts"] = zalo_quota_metrics.evaluate_alerts(snap)
    return snap
