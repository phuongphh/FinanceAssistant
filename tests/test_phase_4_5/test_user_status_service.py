"""Phase 4.5 / E5 #5.2 — shared user lifecycle classifier.

``classify_status`` was lifted out of ``backend/api/admin/users.py`` so the
admin console and the re-engagement broadcast agree on "dormant". These tests
pin the buckets with an injected ``now`` (deterministic, no wall clock) and
prove the admin router still exposes the same behaviour through its
``_classify_status`` alias.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.api.admin import users as admin_users
from backend.services.user_status_service import (
    STATUS_ACTIVE,
    STATUS_AT_RISK,
    STATUS_DORMANT,
    STATUS_NEW,
    STATUS_SUSPENDED,
    STATUSES,
    classify_status,
)

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


def test_suspended_override_wins_over_everything():
    # Even a brand-new, just-active user reads as suspended when overridden.
    assert (
        classify_status(NOW, NOW, "suspended", now=NOW) == STATUS_SUSPENDED
    )


def test_new_when_joined_within_three_days():
    created = NOW - timedelta(days=1)
    assert classify_status(created, None, None, now=NOW) == STATUS_NEW


def test_dormant_when_never_active():
    created = NOW - timedelta(days=30)
    assert classify_status(created, None, None, now=NOW) == STATUS_DORMANT


def test_dormant_when_last_active_over_seven_days():
    created = NOW - timedelta(days=30)
    last = NOW - timedelta(days=8)
    assert classify_status(created, last, None, now=NOW) == STATUS_DORMANT


def test_at_risk_between_three_and_seven_days():
    created = NOW - timedelta(days=30)
    last = NOW - timedelta(days=5)
    assert classify_status(created, last, None, now=NOW) == STATUS_AT_RISK


def test_active_when_recently_seen():
    created = NOW - timedelta(days=30)
    last = NOW - timedelta(hours=6)
    assert classify_status(created, last, None, now=NOW) == STATUS_ACTIVE


def test_naive_timestamps_are_treated_as_utc():
    # A tz-naive created_at must not raise on the ``now - created`` subtraction.
    created = (NOW - timedelta(days=30)).replace(tzinfo=None)
    last = (NOW - timedelta(days=10)).replace(tzinfo=None)
    assert classify_status(created, last, None, now=NOW) == STATUS_DORMANT


def test_now_defaults_to_wall_clock():
    # No ``now`` kwarg still works (uses datetime.now) — a very old user is dormant.
    created = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert classify_status(created, None, None) == STATUS_DORMANT


def test_admin_router_alias_matches_service():
    created = NOW - timedelta(days=30)
    last = NOW - timedelta(days=8)
    # The admin console keeps the same name and delegates to the shared service.
    assert admin_users._classify_status is classify_status
    assert admin_users._classify_status(created, last, None) == STATUS_DORMANT


def test_admin_statuses_set_matches_shared():
    assert admin_users.STATUSES == set(STATUSES)
