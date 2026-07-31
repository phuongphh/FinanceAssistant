"""User lifecycle status — shared classifier.

Extracted from ``backend/api/admin/users.py`` (Phase 4.5 / E5 #5.2) so the
admin console and the one-time re-engagement broadcast
(``scripts/send_reengagement_broadcast.py``) agree on exactly what "dormant"
means. There must be one definition of the funnel, not two that drift.

Pure and DB-free: it takes the two timestamps plus the manual override and
returns a status string. The caller owns the DB reads that produce those
timestamps (``created_at`` from ``users``, ``last_active_at`` from the max
conversation turn). ``now`` is injectable so tests are deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

STATUS_ACTIVE = "active"
STATUS_AT_RISK = "at_risk"
STATUS_DORMANT = "dormant"
STATUS_NEW = "new"
STATUS_SUSPENDED = "suspended"

STATUSES = frozenset(
    {STATUS_ACTIVE, STATUS_AT_RISK, STATUS_DORMANT, STATUS_NEW, STATUS_SUSPENDED}
)

# Windows that bucket a user by recency. Kept as module constants so both the
# admin console and the broadcast cohort read from the same numbers.
_NEW_WINDOW = timedelta(days=3)
_AT_RISK_AFTER = timedelta(days=3)
_DORMANT_AFTER = timedelta(days=7)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def classify_status(
    created_at: datetime,
    last_active_at: datetime | None,
    manual_status: str | None,
    *,
    now: datetime | None = None,
) -> str:
    """Bucket a user into a lifecycle status.

    * ``manual_status == "suspended"`` always wins (operator override).
    * Joined < 3 days ago → ``new`` (too fresh to judge engagement).
    * Never active, or last active > 7 days ago → ``dormant``.
    * Last active > 3 days ago → ``at_risk``.
    * Otherwise → ``active``.
    """
    if manual_status == STATUS_SUSPENDED:
        return STATUS_SUSPENDED
    now = now or datetime.now(timezone.utc)
    created = _as_utc(created_at)
    last_active = _as_utc(last_active_at)
    if now - created < _NEW_WINDOW:
        return STATUS_NEW
    if last_active is None or now - last_active > _DORMANT_AFTER:
        return STATUS_DORMANT
    if now - last_active > _AT_RISK_AFTER:
        return STATUS_AT_RISK
    return STATUS_ACTIVE


__all__ = [
    "classify_status",
    "STATUS_ACTIVE",
    "STATUS_AT_RISK",
    "STATUS_DORMANT",
    "STATUS_NEW",
    "STATUS_SUSPENDED",
    "STATUSES",
]
