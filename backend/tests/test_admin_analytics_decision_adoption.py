"""Phase 4.6 / E4 / Issue #4.2 — the decision-adoption admin chart.

``GET /charts/decision-adoption`` reads the append-only ``decision_query_logs``
(tagged with an onboarding cohort in #4.1) and reports, per ISO week × cohort:
interactions, active users, interactions/user, and the average độ nét. The
endpoint is DB-free under test — a ``_FakeDB`` replays the single grouped query
and ``cache_get`` / ``cache_set`` are monkeypatched.

Coverage: cache key + tenant scoping, cohort splitting (reset / legacy /
unattributed) in a fixed display order, dense per-week backfill of gaps,
``interactions_per_user`` rounding, ``avg_clarity`` ``None`` passthrough,
zero-interaction cohort skipping, the cache-hit short-circuit, and the
aggregate-only (no-PII) shape of the payload.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from backend.api.admin import analytics as admin_analytics
from backend.api.admin.analytics import VN_TZ, COHORT_UNATTRIBUTED
from backend.models.admin_user import AdminUser
from backend.models.user import User


class _Row:
    def __init__(self, **values):
        self.__dict__.update(values)
        self._values = list(values.values())

    def __getitem__(self, index: int):
        return self._values[index]


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


def _admin(tenant_id: int | None = 1) -> AdminUser:
    return AdminUser(
        id=1,
        email="admin@example.com",
        password_hash="hash",
        role="super_admin",
        tenant_id=tenant_id,
        is_active=True,
    )


def _current_week() -> date:
    """Monday of the current VN week — mirrors the endpoint's bucketing."""
    today = datetime.now(VN_TZ).date()
    return today - timedelta(days=today.weekday())


@pytest.fixture
def cache_spy(monkeypatch):
    """Monkeypatch the cache; return (get_keys, set_calls, seed)."""
    get_keys: list[str] = []
    set_calls: list[tuple] = []
    seeded: dict[str, object] = {}

    async def fake_cache_get(key):
        get_keys.append(key)
        return seeded.get(key)

    async def fake_cache_set(key, value, ttl):
        set_calls.append((key, value, ttl))

    monkeypatch.setattr(admin_analytics, "cache_get", fake_cache_get)
    monkeypatch.setattr(admin_analytics, "cache_set", fake_cache_set)
    return get_keys, set_calls, seeded


# --------------------------------------------------------------------------
# tenant scoping — decision_query_logs has no tenant_id column, so the query
# joins ``users`` and scopes by ``users.tenant_id`` (no cross-tenant leak).
# --------------------------------------------------------------------------


def test_user_tenant_filter_scopes_by_users_column():
    # decision_query_logs has no tenant_id, so scoping rides on users.tenant_id;
    # every tenant (default or not) gets a real column predicate, not true/false.
    assert str(admin_analytics._tenant_filter(User, 1)).startswith("users.tenant_id")
    assert str(admin_analytics._tenant_filter(User, 2)).startswith("users.tenant_id")


@pytest.mark.asyncio
async def test_query_scopes_via_users_tenant_column(cache_spy):
    _, _, _ = cache_spy
    db = _FakeDB([_RowsResult([])])

    await admin_analytics.decision_adoption(weeks=4, admin=_admin(2), db=db)

    # The join+where scopes by users.tenant_id, not a decision_query_logs guard.
    compiled = str(db.statements[0])
    assert "users.tenant_id" in compiled
    assert "users.deleted_at" in compiled


@pytest.mark.asyncio
async def test_clarity_is_averaged_per_active_user_not_per_interaction(cache_spy):
    """độ nét (G2) is a per-active-user average, so the query rolls up by
    user_id first (inner group-by) then averages those per-user means — a chatty
    user cannot skew the cohort's độ nét by sheer interaction count."""
    _, _, _ = cache_spy
    db = _FakeDB([_RowsResult([])])

    await admin_analytics.decision_adoption(weeks=4, admin=_admin(1), db=db)

    compiled = str(db.statements[0])
    # A nested subquery grouped by user_id feeds the outer per-cohort average.
    assert "decision_query_logs.user_id" in compiled
    assert "GROUP BY" in compiled.upper()


# --------------------------------------------------------------------------
# happy path — split cohorts, dense backfill, rounding
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_splits_cohorts_and_backfills_missing_weeks(cache_spy):
    get_keys, set_calls, _ = cache_spy
    w = _current_week()
    weeks = [w - timedelta(weeks=3), w - timedelta(weeks=2), w - timedelta(weeks=1), w]

    db = _FakeDB([
        _RowsResult([
            _Row(week=weeks[0], cohort="reset", interactions=4, active_users=2, avg_clarity=Decimal("8.0")),
            _Row(week=weeks[3], cohort="reset", interactions=3, active_users=3, avg_clarity=6.5),
            _Row(week=weeks[2], cohort="legacy", interactions=2, active_users=1, avg_clarity=None),
        ])
    ])

    response = await admin_analytics.decision_adoption(weeks=4, admin=_admin(1), db=db)

    assert get_keys == ["admin:tenant:1:charts:decision-adoption:4"]
    assert set_calls[0][0] == "admin:tenant:1:charts:decision-adoption:4"
    assert set_calls[0][2] == 1800

    assert response["weeks"] == weeks
    # reset first, legacy second (unattributed absent), matching label order.
    assert [c["cohort"] for c in response["cohorts"]] == ["reset", "legacy"]
    assert [c["label"] for c in response["cohorts"]] == ["Segment mới (reset)", "Cohort cũ (legacy)"]

    reset = response["cohorts"][0]["points"]
    assert [p["week"] for p in reset] == weeks  # dense: one point per week
    assert reset[0] == {
        "week": weeks[0],
        "interactions": 4,
        "active_users": 2,
        "interactions_per_user": 2.0,
        "avg_clarity": 8.0,
    }
    # gap weeks are back-filled with zeros / None, never dropped.
    assert reset[1] == {
        "week": weeks[1],
        "interactions": 0,
        "active_users": 0,
        "interactions_per_user": 0.0,
        "avg_clarity": None,
    }
    assert reset[3]["interactions"] == 3
    assert reset[3]["interactions_per_user"] == 1.0
    assert reset[3]["avg_clarity"] == 6.5

    legacy = response["cohorts"][1]["points"]
    assert legacy[2]["interactions"] == 2
    assert legacy[2]["active_users"] == 1
    assert legacy[2]["interactions_per_user"] == 2.0
    assert legacy[2]["avg_clarity"] is None  # NULL avg → None, no crash


@pytest.mark.asyncio
async def test_interactions_per_user_rounds_to_two_places(cache_spy):
    w = _current_week()
    db = _FakeDB([
        _RowsResult([
            _Row(week=w, cohort="reset", interactions=5, active_users=3, avg_clarity=Decimal("7.25")),
        ])
    ])

    response = await admin_analytics.decision_adoption(weeks=1, admin=_admin(1), db=db)

    point = response["cohorts"][0]["points"][0]
    assert point["interactions_per_user"] == round(5 / 3, 2)  # 1.67
    assert point["avg_clarity"] == 7.2  # round(7.25, 1) → banker's/half-even


# --------------------------------------------------------------------------
# the unattributed bucket + zero-cohort skipping + ordering
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_null_cohort_surfaces_as_unattributed(cache_spy):
    w = _current_week()
    # coalesce() happens in SQL, so the fake row already carries the label.
    db = _FakeDB([
        _RowsResult([
            _Row(week=w, cohort=COHORT_UNATTRIBUTED, interactions=1, active_users=1, avg_clarity=None),
        ])
    ])

    response = await admin_analytics.decision_adoption(weeks=1, admin=_admin(1), db=db)

    assert [c["cohort"] for c in response["cohorts"]] == [COHORT_UNATTRIBUTED]
    assert response["cohorts"][0]["label"] == "Chưa gắn cohort"


@pytest.mark.asyncio
async def test_zero_interaction_cohorts_are_skipped(cache_spy):
    w = _current_week()
    db = _FakeDB([
        _RowsResult([
            _Row(week=w, cohort="legacy", interactions=2, active_users=2, avg_clarity=None),
        ])
    ])

    response = await admin_analytics.decision_adoption(weeks=2, admin=_admin(1), db=db)

    # Only the cohort with rows appears; reset / unattributed are omitted.
    assert [c["cohort"] for c in response["cohorts"]] == ["legacy"]


@pytest.mark.asyncio
async def test_all_three_cohorts_keep_label_order(cache_spy):
    w = _current_week()
    db = _FakeDB([
        _RowsResult([
            # deliberately out of order — output order comes from the label map.
            _Row(week=w, cohort=COHORT_UNATTRIBUTED, interactions=1, active_users=1, avg_clarity=None),
            _Row(week=w, cohort="legacy", interactions=1, active_users=1, avg_clarity=None),
            _Row(week=w, cohort="reset", interactions=1, active_users=1, avg_clarity=None),
        ])
    ])

    response = await admin_analytics.decision_adoption(weeks=1, admin=_admin(1), db=db)

    assert [c["cohort"] for c in response["cohorts"]] == ["reset", "legacy", COHORT_UNATTRIBUTED]


# --------------------------------------------------------------------------
# empty window, cache short-circuit, PII shape
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_window_returns_weeks_but_no_cohorts(cache_spy):
    w = _current_week()
    db = _FakeDB([_RowsResult([])])

    response = await admin_analytics.decision_adoption(weeks=3, admin=_admin(1), db=db)

    assert response["cohorts"] == []
    assert response["weeks"] == [w - timedelta(weeks=2), w - timedelta(weeks=1), w]


@pytest.mark.asyncio
async def test_cache_hit_short_circuits_the_query(cache_spy):
    get_keys, set_calls, seeded = cache_spy
    key = "admin:tenant:1:charts:decision-adoption:8"
    seeded[key] = {"weeks": [], "cohorts": [], "cached": True}
    db = _FakeDB([])  # would IndexError if execute() were called

    response = await admin_analytics.decision_adoption(weeks=8, admin=_admin(1), db=db)

    assert response == {"weeks": [], "cohorts": [], "cached": True}
    assert get_keys == [key]
    assert set_calls == []  # nothing re-cached on a hit
    assert db.statements == []


@pytest.mark.asyncio
async def test_payload_is_aggregate_only_no_user_ids(cache_spy):
    w = _current_week()
    db = _FakeDB([
        _RowsResult([
            _Row(week=w, cohort="reset", interactions=3, active_users=2, avg_clarity=Decimal("5.0")),
        ])
    ])

    response = await admin_analytics.decision_adoption(weeks=1, admin=_admin(1), db=db)

    point_keys = set(response["cohorts"][0]["points"][0].keys())
    assert point_keys == {"week", "interactions", "active_users", "interactions_per_user", "avg_clarity"}
    # no user-identifying field ever leaves the aggregate query.
    assert not any("user_id" in k or "phone" in k or "email" in k for k in point_keys)
