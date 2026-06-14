"""Admin feedback browser — unit tests.

Covers the operator-facing "all feedback" subpage added to the admin portal:

- ``_parse_window`` — ``all`` applies no time predicate, ``custom`` anchors to
  VN_TZ midnight, named periods reuse the shared PERIOD_DAYS map
- ``_parse_user_id`` — UUID parse + 422 on garbage
- ``_validate_enums`` — 422 on bad category/sentiment/priority/status/sort
- ``_build_filters`` — tenant isolation via JOIN to users (Feedback has no
  tenant_id), soft-deleted users excluded, every filter predicate present
- ``_row_to_item`` — PII masking (mask_name) + safe float/None coercion
- ``_order_by`` — newest/oldest deterministic tie-breaker
- ``GET /feedback`` — returns total + items, audits, commits
- ``GET /feedback/export.csv`` — RFC-4180 escaping, X-* headers, truncation
"""

from __future__ import annotations

import csv
import io
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from backend.api.admin import feedback as fb
from backend.api.admin.analytics import VN_TZ


# ---------- helpers ----------------------------------------------------------


def _compile_sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _compile_filters(filters) -> str:
    return " ".join(_compile_sql(f) for f in filters)


def _make_row(**overrides):
    """A SimpleNamespace shaped like the list-query result row."""
    base = dict(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        content="App rất tốt",
        category="praise",
        sentiment="positive",
        priority="low",
        status="new",
        trigger="passive_command",
        classification_confidence=0.91,
        onboarding_emoji_signal=None,
        created_at=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        first_responded_at=None,
        display_name="Nguyễn Văn An",
        telegram_handle="annguyen",
        telegram_id=12345,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_csv_row(**overrides):
    """A SimpleNamespace shaped like the CSV-query result row."""
    base = dict(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        created_at=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
        user_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        category="bug",
        sentiment="negative",
        priority="high",
        status="reviewing",
        trigger="passive_command",
        classification_confidence=0.77,
        onboarding_emoji_signal=None,
        first_responded_at=None,
        content="Bình thường",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Returns a queued scalar then queued execute rows; records commits."""

    def __init__(self, *, scalar=0, rows=None):
        self._scalar = scalar
        self._rows = rows or []
        self.executed = []
        self.commits = 0

    async def scalar(self, stmt):
        self.executed.append(("scalar", stmt))
        return self._scalar

    async def execute(self, stmt):
        self.executed.append(("execute", stmt))
        return _FakeResult(self._rows)

    async def commit(self):
        self.commits += 1


def _admin(tenant_id=7, admin_id=42):
    return SimpleNamespace(id=admin_id, tenant_id=tenant_id)


def _patch_log(monkeypatch):
    calls: list[dict] = []

    async def fake_log(db, admin_id, action, **kwargs):
        calls.append({"admin_id": admin_id, "action": action, **kwargs})
        return SimpleNamespace(id=1)

    monkeypatch.setattr(fb, "log_action", fake_log)
    return calls


# ---------- _parse_window ----------------------------------------------------


def test_parse_window_all_applies_no_time_predicate():
    start, end, label = fb._parse_window("all", None, None)
    assert start is None
    assert end is None
    assert label == "all"


def test_parse_window_custom_anchored_to_vn_tz_midnight():
    start, end, label = fb._parse_window(
        "custom", date(2026, 5, 1), date(2026, 5, 7)
    )
    expected_start = datetime.combine(
        date(2026, 5, 1), time.min, tzinfo=VN_TZ
    ).astimezone(timezone.utc)
    # end is half-open: start of the day AFTER end_date
    expected_end = datetime.combine(
        date(2026, 5, 8), time.min, tzinfo=VN_TZ
    ).astimezone(timezone.utc)
    assert start == expected_start
    assert end == expected_end
    # 00:00 ICT == 17:00 UTC the previous day — proves we did not use naive UTC.
    assert start.hour == 17
    assert label == "custom:2026-05-01:2026-05-07"


def test_parse_window_custom_single_day_is_one_day_wide():
    start, end, _ = fb._parse_window("custom", date(2026, 5, 1), date(2026, 5, 1))
    assert end - start == timedelta(days=1)


def test_parse_window_named_period_uses_period_days():
    before = fb._now()
    start, end, label = fb._parse_window("7d", None, None)
    after = fb._now()
    assert label == "7d"
    # end ~ now, start ~ now - 7d (allow for the tiny window between _now calls)
    assert before - timedelta(days=7) - timedelta(seconds=1) <= start
    assert start <= after - timedelta(days=7) + timedelta(seconds=1)
    assert before - timedelta(seconds=1) <= end <= after + timedelta(seconds=1)


def test_parse_window_custom_without_dates_falls_back_to_default_days():
    # "custom" with missing dates must not crash — falls through to 30d default.
    start, end, label = fb._parse_window("custom", None, None)
    assert start is not None and end is not None
    assert label == "custom"
    assert timedelta(days=29) < (end - start) < timedelta(days=31)


# ---------- _parse_user_id ---------------------------------------------------


def test_parse_user_id_accepts_valid_uuid():
    raw = "22222222-2222-2222-2222-222222222222"
    assert fb._parse_user_id(raw) == uuid.UUID(raw)


@pytest.mark.parametrize("bad", ["not-a-uuid", "123", "", "  "])
def test_parse_user_id_rejects_garbage(bad):
    with pytest.raises(HTTPException) as exc:
        fb._parse_user_id(bad)
    assert exc.value.status_code == 422
    assert exc.value.detail == "Invalid user_id"


# ---------- _validate_enums --------------------------------------------------


def test_validate_enums_accepts_valid_and_none():
    # None means "no filter" — must never raise.
    fb._validate_enums(None, None, None, None, "newest")
    fb._validate_enums("bug", "negative", "high", "new", "oldest")


@pytest.mark.parametrize(
    "args,detail",
    [
        (("nope", None, None, None, "newest"), "Invalid category"),
        ((None, "meh", None, None, "newest"), "Invalid sentiment"),
        ((None, None, "urgent", None, "newest"), "Invalid priority"),
        ((None, None, None, "open", "newest"), "Invalid status"),
        ((None, None, None, None, "sideways"), "Invalid sort"),
    ],
)
def test_validate_enums_rejects_bad_values(args, detail):
    with pytest.raises(HTTPException) as exc:
        fb._validate_enums(*args)
    assert exc.value.status_code == 422
    assert exc.value.detail == detail


# ---------- _build_filters ---------------------------------------------------


def test_build_filters_always_scopes_to_tenant_and_excludes_deleted():
    filters = fb._build_filters(
        7,
        start=None,
        end=None,
        category=None,
        sentiment=None,
        priority=None,
        status_=None,
        user_uuid=None,
        search=None,
    )
    sql = _compile_filters(filters)
    # Tenant isolation is non-negotiable: an operator may never read another
    # tenant's feedback, and soft-deleted users are excluded for parity.
    assert "users.tenant_id = 7" in sql
    assert "users.deleted_at IS NULL" in sql
    # With the "all" window no created_at predicate is emitted.
    assert "feedbacks.created_at" not in sql


def test_build_filters_includes_every_predicate_when_supplied():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = datetime(2026, 5, 8, tzinfo=timezone.utc)
    uid = uuid.UUID("22222222-2222-2222-2222-222222222222")
    filters = fb._build_filters(
        1,
        start=start,
        end=end,
        category="bug",
        sentiment="negative",
        priority="high",
        status_="new",
        user_uuid=uid,
        search="crash",
    )
    sql = _compile_filters(filters)
    assert "feedbacks.created_at >=" in sql
    assert "feedbacks.created_at <" in sql
    assert "feedbacks.category = 'bug'" in sql
    assert "feedbacks.sentiment = 'negative'" in sql
    assert "feedbacks.priority = 'high'" in sql
    assert "feedbacks.status = 'new'" in sql
    assert "feedbacks.user_id = " in sql
    # Free-text search hits content OR the (cast) user_id, never silently
    # ignored, and is wrapped as a LIKE pattern.
    assert "%crash%" in sql
    assert "feedbacks.content ILIKE" in sql


def test_build_filters_search_is_trimmed():
    filters = fb._build_filters(
        1,
        start=None,
        end=None,
        category=None,
        sentiment=None,
        priority=None,
        status_=None,
        user_uuid=None,
        search="  spaced  ",
    )
    sql = _compile_filters(filters)
    assert "%spaced%" in sql
    assert "% spaced %" not in sql


# ---------- _order_by --------------------------------------------------------


def test_order_by_newest_is_descending_with_id_tiebreaker():
    clauses = fb._order_by("newest")
    sql = " ".join(_compile_sql(c) for c in clauses)
    assert "feedbacks.created_at DESC" in sql
    assert "feedbacks.id DESC" in sql


def test_order_by_oldest_is_ascending_with_id_tiebreaker():
    clauses = fb._order_by("oldest")
    sql = " ".join(_compile_sql(c) for c in clauses)
    assert "feedbacks.created_at ASC" in sql
    assert "feedbacks.id ASC" in sql


# ---------- _row_to_item -----------------------------------------------------


def test_row_to_item_masks_display_name():
    item = fb._row_to_item(_make_row(display_name="Nguyễn Văn An"))
    # PII never leaves the building in the clear.
    assert item.display_name == "Nguyễn V. A."
    assert item.user_id == "22222222-2222-2222-2222-222222222222"
    assert item.classification_confidence == pytest.approx(0.91)


def test_row_to_item_falls_back_to_handle_then_em_dash():
    item = fb._row_to_item(_make_row(display_name=None, telegram_handle="annguyen"))
    assert item.display_name == "annguyen"
    blank = fb._row_to_item(
        _make_row(display_name=None, telegram_handle=None)
    )
    assert blank.display_name == "—"


def test_row_to_item_handles_null_confidence_and_timestamps():
    item = fb._row_to_item(
        _make_row(classification_confidence=None, first_responded_at=None)
    )
    assert item.classification_confidence is None
    assert item.first_responded_at is None
    assert item.created_at == "2026-06-01T09:30:00+00:00"


# ---------- GET /feedback ----------------------------------------------------


@pytest.mark.asyncio
async def test_list_feedback_returns_total_items_and_audits(monkeypatch):
    calls = _patch_log(monkeypatch)
    db = _FakeDB(scalar=2, rows=[_make_row(), _make_row()])

    resp = await fb.list_feedback(
        request=None,
        period="all",
        start_date=None,
        end_date=None,
        category=None,
        sentiment=None,
        priority=None,
        status=None,
        user_id=None,
        search=None,
        sort="newest",
        limit=50,
        offset=0,
        admin=_admin(),
        db=db,
    )

    assert resp.total == 2
    assert resp.limit == 50
    assert resp.offset == 0
    assert len(resp.items) == 2
    assert resp.items[0].display_name == "Nguyễn V. A."
    # Exactly one count + one list query, and the request is audited + committed.
    assert [kind for kind, _ in db.executed] == ["scalar", "execute"]
    assert db.commits == 1
    assert calls and calls[0]["action"] == "feedback_list"
    assert calls[0]["payload"]["returned"] == 2


@pytest.mark.asyncio
async def test_list_feedback_tenant_scopes_both_queries(monkeypatch):
    _patch_log(monkeypatch)
    db = _FakeDB(scalar=0, rows=[])

    await fb.list_feedback(
        request=None,
        period="all",
        start_date=None,
        end_date=None,
        category=None,
        sentiment=None,
        priority=None,
        status=None,
        user_id=None,
        search=None,
        sort="newest",
        limit=50,
        offset=0,
        admin=_admin(tenant_id=7),
        db=db,
    )

    for _, stmt in db.executed:
        assert "users.tenant_id = 7" in _compile_sql(stmt)


@pytest.mark.asyncio
async def test_list_feedback_rejects_bad_enum_before_touching_db(monkeypatch):
    calls = _patch_log(monkeypatch)
    db = _FakeDB(scalar=0, rows=[])

    with pytest.raises(HTTPException) as exc:
        await fb.list_feedback(
            request=None,
            period="all",
            start_date=None,
            end_date=None,
            category="bogus",
            sentiment=None,
            priority=None,
            status=None,
            user_id=None,
            search=None,
            sort="newest",
            limit=50,
            offset=0,
            admin=_admin(),
            db=db,
        )
    assert exc.value.status_code == 422
    # Fail fast: no query, no audit, no commit on a malformed request.
    assert db.executed == []
    assert db.commits == 0
    assert calls == []


@pytest.mark.asyncio
async def test_list_feedback_rejects_bad_user_id(monkeypatch):
    _patch_log(monkeypatch)
    db = _FakeDB(scalar=0, rows=[])
    with pytest.raises(HTTPException) as exc:
        await fb.list_feedback(
            request=None,
            period="all",
            start_date=None,
            end_date=None,
            category=None,
            sentiment=None,
            priority=None,
            status=None,
            user_id="not-a-uuid",
            search=None,
            sort="newest",
            limit=50,
            offset=0,
            admin=_admin(),
            db=db,
        )
    assert exc.value.status_code == 422
    assert db.executed == []


# ---------- GET /feedback/export.csv -----------------------------------------


@pytest.mark.asyncio
async def test_export_csv_escapes_content_and_sets_headers(monkeypatch):
    calls = _patch_log(monkeypatch)
    nasty = 'has, comma "quote" and\nnewline'
    db = _FakeDB(scalar=1, rows=[_make_csv_row(content=nasty)])

    resp = await fb.export_feedback_csv(
        request=None,
        period="all",
        start_date=None,
        end_date=None,
        category=None,
        sentiment=None,
        priority=None,
        status=None,
        user_id=None,
        search=None,
        sort="newest",
        admin=_admin(),
        db=db,
    )

    assert resp.media_type == "text/csv"
    assert resp.headers["X-Rows-Returned"] == "1"
    assert resp.headers["X-Rows-Total"] == "1"
    assert resp.headers["X-Truncated"] == "false"
    assert "attachment" in resp.headers["Content-Disposition"]

    # Round-trip through the csv reader: the nasty content survives intact,
    # proving quoting/escaping is correct (no column bleed / CSV injection).
    text = resp.body.decode("utf-8")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == fb.CSV_COLUMNS
    assert parsed[1][fb.CSV_COLUMNS.index("content")] == nasty
    assert parsed[1][fb.CSV_COLUMNS.index("category")] == "bug"

    # Export is an exfiltration-sensitive action and must be audited + committed.
    assert calls and calls[0]["action"] == "feedback_export"
    assert calls[0]["commit"] is True


@pytest.mark.asyncio
async def test_export_csv_marks_truncated_when_total_exceeds_returned(monkeypatch):
    calls = _patch_log(monkeypatch)
    # scalar (total) is larger than the number of rows returned -> truncated.
    db = _FakeDB(scalar=5, rows=[_make_csv_row(), _make_csv_row()])

    resp = await fb.export_feedback_csv(
        request=None,
        period="all",
        start_date=None,
        end_date=None,
        category=None,
        sentiment=None,
        priority=None,
        status=None,
        user_id=None,
        search=None,
        sort="newest",
        admin=_admin(),
        db=db,
    )

    assert resp.headers["X-Rows-Total"] == "5"
    assert resp.headers["X-Rows-Returned"] == "2"
    assert resp.headers["X-Truncated"] == "true"
    assert calls[0]["payload"]["truncated"] is True


@pytest.mark.asyncio
async def test_export_csv_tenant_scopes_query(monkeypatch):
    _patch_log(monkeypatch)
    db = _FakeDB(scalar=0, rows=[])

    await fb.export_feedback_csv(
        request=None,
        period="all",
        start_date=None,
        end_date=None,
        category=None,
        sentiment=None,
        priority=None,
        status=None,
        user_id=None,
        search=None,
        sort="newest",
        admin=_admin(tenant_id=3),
        db=db,
    )

    for _, stmt in db.executed:
        assert "users.tenant_id = 3" in _compile_sql(stmt)
