"""Phase 4.6 / E4 / Issue #4.2 — the decision-retention admin chart.

``GET /charts/decision-retention`` reads ``users`` (left-joined to
``onboarding_sessions`` for the cohort goal) plus ``events`` and reports a
classic signup→week-N retention curve per onboarding cohort (reset / legacy /
unattributed), headlined by D28 (offset 4, ≈28 days) — the metric behind gate
G2. The endpoint is DB-free under test: a ``_FakeDB`` replays the two queries
(users, then activity) and ``cache_get`` / ``cache_set`` are monkeypatched.

Coverage: cache key + tenant scoping via ``users.tenant_id``, cohort bucketing
from ``goal_choice`` (reset / legacy / unattributed), the shrinking ``eligible``
denominator for later offsets, D28 (w4) computation, ``None`` where no user is
old enough, the cohort-skip + label order, the cache-hit short-circuit, and the
aggregate-only (no-PII) shape of the payload.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

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


def _cohort(response, name):
    return next(c for c in response["cohorts"] if c["cohort"] == name)


# --------------------------------------------------------------------------
# tenant scoping — users has tenant_id, so the query scopes by users.tenant_id
# and left-joins onboarding_sessions for the cohort goal (no cross-tenant leak).
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_scopes_via_users_tenant_column(cache_spy):
    db = _FakeDB([_RowsResult([])])  # no users → activity query is skipped

    await admin_analytics.decision_retention(weeks=8, admin=_admin(2), db=db)

    compiled = str(db.statements[0])
    assert "users.tenant_id" in compiled
    assert "users.deleted_at" in compiled
    assert "onboarding_sessions" in compiled  # left join carries the cohort goal


# --------------------------------------------------------------------------
# happy path — cohort bucketing, shrinking eligible denominator, D28
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buckets_cohorts_and_computes_d28(cache_spy):
    get_keys, set_calls, _ = cache_spy
    w = _current_week()
    signup_4wk = w - timedelta(weeks=4)  # max_elapsed == 4 → eligible through w4

    users = _RowsResult([
        _Row(id="A", signup_week=signup_4wk, goal_choice="emergency_fund"),  # reset
        _Row(id="B", signup_week=signup_4wk, goal_choice="first_home"),      # reset
        _Row(id="C", signup_week=w, goal_choice="understand_wealth"),        # legacy (too new)
        _Row(id="D", signup_week=signup_4wk, goal_choice=None),              # unattributed
    ])
    activity = _RowsResult([
        _Row(user_id="A", active_week=signup_4wk),  # w0
        _Row(user_id="A", active_week=w),           # w4 — A is D28-retained
        _Row(user_id="B", active_week=signup_4wk),  # w0 only — B drops before w4
        _Row(user_id="C", active_week=w),           # w0
        _Row(user_id="D", active_week=signup_4wk),  # w0 only
    ])
    db = _FakeDB([users, activity])

    response = await admin_analytics.decision_retention(weeks=8, admin=_admin(1), db=db)

    assert get_keys == ["admin:tenant:1:charts:decision-retention:8"]
    assert set_calls[0][0] == "admin:tenant:1:charts:decision-retention:8"
    assert set_calls[0][2] == 86400
    assert response["weeks"] == 8

    reset = _cohort(response, "reset")
    assert reset["label"] == "Segment mới (reset)"
    assert reset["cohort_size"] == 2
    # Both reset users are old enough for w0..w4; nobody is old enough for w5+.
    assert reset["eligible"]["w4"] == 2
    assert reset["eligible"]["w5"] == 0
    assert reset["retention"]["w0"] == 100
    assert reset["retention"]["w1"] == 0  # nobody active at offset 1
    assert reset["retention"]["w4"] == 50  # A retained, B not → 1/2
    assert reset["retention"]["w5"] is None  # no eligible user yet
    assert reset["d28"] == 50

    legacy = _cohort(response, "legacy")
    assert legacy["cohort_size"] == 1
    assert legacy["eligible"]["w4"] == 0  # C signed up this week
    assert legacy["retention"]["w0"] == 100
    assert legacy["retention"]["w4"] is None
    assert legacy["d28"] is None

    unattributed = _cohort(response, COHORT_UNATTRIBUTED)
    assert unattributed["label"] == "Chưa gắn cohort"
    assert unattributed["cohort_size"] == 1
    assert unattributed["eligible"]["w4"] == 1
    assert unattributed["retention"]["w4"] == 0  # D never returned
    assert unattributed["d28"] == 0


@pytest.mark.asyncio
async def test_cohorts_keep_label_order(cache_spy):
    w = _current_week()
    old = w - timedelta(weeks=4)
    users = _RowsResult([
        # deliberately out of label order — output order comes from the map.
        _Row(id="D", signup_week=old, goal_choice=None),
        _Row(id="C", signup_week=old, goal_choice="track_spending"),
        _Row(id="A", signup_week=old, goal_choice="wedding"),
    ])
    activity = _RowsResult([])
    db = _FakeDB([users, activity])

    response = await admin_analytics.decision_retention(weeks=8, admin=_admin(1), db=db)

    assert [c["cohort"] for c in response["cohorts"]] == ["reset", "legacy", COHORT_UNATTRIBUTED]


@pytest.mark.asyncio
async def test_cohort_with_no_users_is_skipped(cache_spy):
    w = _current_week()
    users = _RowsResult([
        _Row(id="A", signup_week=w - timedelta(weeks=4), goal_choice="first_home"),
    ])
    activity = _RowsResult([_Row(user_id="A", active_week=w - timedelta(weeks=4))])
    db = _FakeDB([users, activity])

    response = await admin_analytics.decision_retention(weeks=8, admin=_admin(1), db=db)

    assert [c["cohort"] for c in response["cohorts"]] == ["reset"]


# --------------------------------------------------------------------------
# short window, empty window, cache short-circuit, PII shape
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_d28_is_none_when_window_shorter_than_five_weeks(cache_spy):
    w = _current_week()
    users = _RowsResult([
        _Row(id="A", signup_week=w - timedelta(weeks=3), goal_choice="wedding"),
    ])
    activity = _RowsResult([_Row(user_id="A", active_week=w - timedelta(weeks=3))])
    db = _FakeDB([users, activity])

    response = await admin_analytics.decision_retention(weeks=4, admin=_admin(1), db=db)

    reset = _cohort(response, "reset")
    assert "w4" not in reset["retention"]  # window stops at w3
    assert reset["d28"] is None


@pytest.mark.asyncio
async def test_empty_window_skips_activity_query(cache_spy):
    db = _FakeDB([_RowsResult([])])  # only the users query runs

    response = await admin_analytics.decision_retention(weeks=6, admin=_admin(1), db=db)

    assert response == {"weeks": 6, "cohorts": []}
    assert len(db.statements) == 1  # activity query short-circuited


@pytest.mark.asyncio
async def test_cache_hit_short_circuits_the_query(cache_spy):
    get_keys, set_calls, seeded = cache_spy
    key = "admin:tenant:1:charts:decision-retention:8"
    seeded[key] = {"weeks": 8, "cohorts": [], "cached": True}
    db = _FakeDB([])  # would IndexError if execute() were called

    response = await admin_analytics.decision_retention(weeks=8, admin=_admin(1), db=db)

    assert response == {"weeks": 8, "cohorts": [], "cached": True}
    assert get_keys == [key]
    assert set_calls == []
    assert db.statements == []


@pytest.mark.asyncio
async def test_payload_is_aggregate_only_no_user_ids(cache_spy):
    w = _current_week()
    users = _RowsResult([
        _Row(id="A", signup_week=w - timedelta(weeks=4), goal_choice="emergency_fund"),
    ])
    activity = _RowsResult([_Row(user_id="A", active_week=w - timedelta(weeks=4))])
    db = _FakeDB([users, activity])

    response = await admin_analytics.decision_retention(weeks=8, admin=_admin(1), db=db)

    cohort_keys = set(response["cohorts"][0].keys())
    assert cohort_keys == {"cohort", "label", "cohort_size", "retention", "eligible", "d28"}
    assert not any("user_id" in k or "phone" in k or "email" in k for k in cohort_keys)


def test_tenant_filter_scopes_by_users_column():
    assert str(admin_analytics._tenant_filter(User, 1)).startswith("users.tenant_id")
    assert str(admin_analytics._tenant_filter(User, 2)).startswith("users.tenant_id")
