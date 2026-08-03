"""Phase 5.1 #4.2 — a user who exists only on Zalo.

``users.telegram_id`` became nullable so the OA can be a signup channel
(#4.3). Everything here is about the code that used to be allowed to
assume otherwise. Two of these were real breaks, not hypotheticals:

* the admin Pydantic schemas declared ``telegram_id: int`` (required),
  so a single Zalo-only row in the page would raise at serialisation
  time and 500 the entire admin user list — not just that row;
* :func:`resolve_targets` built its Telegram target unconditionally,
  which turns ``None`` into the literal string ``"None"`` and only
  fails after the send has been attempted and dedup-keyed.

The rest assert the proactive senders skip such a user. That is not
merely defensive: Zalo is reactive-first (chốt 02/08/2026), so a
Zalo-only user has no channel that may be spoken to unprompted, and a
job that tries anyway either crashes or silently burns the user's
rate-limit quota on a message nobody receives.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest


def _zalo_only_row(**overrides):
    """A ``users`` row as the admin list query returns it — no Telegram."""
    row = SimpleNamespace(
        id=uuid.uuid4(),
        telegram_id=None,
        telegram_handle=None,
        display_name="Nguyễn Văn An",
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
        manual_status=None,
        last_active_at=datetime.now(timezone.utc),
        messages_total=4,
        tokens_total=90,
        cost_vnd=1_000,
        assets_count=0,
        total_asset_vnd=0,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


# ---------------------------------------------------------------------------
# Admin API — the confirmed break
# ---------------------------------------------------------------------------


def test_admin_list_item_serialises_zalo_only_user():
    from backend.api.admin import users as admin_users

    item = admin_users._row_to_list_item(_zalo_only_row())

    assert item.telegram_id is None
    # The wire payload is what the admin SPA actually consumes; a model
    # that merely constructs but explodes on dump would still 500.
    assert item.model_dump()["telegram_id"] is None


def test_admin_list_response_survives_a_mixed_page():
    """One Zalo-only row must not take the whole page down with it."""
    from backend.api.admin import users as admin_users

    rows = [
        _zalo_only_row(),
        _zalo_only_row(telegram_id=12345, telegram_handle="someone"),
    ]
    response = admin_users.AdminUserListResponse(
        total=2,
        limit=50,
        offset=0,
        users=[admin_users._row_to_list_item(row) for row in rows],
    )

    assert [user.telegram_id for user in response.users] == [None, 12345]


def test_admin_detail_response_accepts_missing_telegram_id():
    from backend.api.admin import users as admin_users

    detail = admin_users.AdminUserDetailResponse(
        user_id=str(uuid.uuid4()),
        telegram_id=None,
        telegram_username=None,
        display_name="Nguyễn V. A.",
        joined_at=datetime.now(timezone.utc).isoformat(),
        tier="starter",
        status="active",
        timeline=[],
        assets=[],
        cost_by_intent=[],
        license=admin_users.LicenseInfo(),
    )

    assert detail.model_dump()["telegram_id"] is None


def test_admin_schemas_do_not_require_telegram_id():
    """Guard the regression directly: the field must stay optional.

    Asserted on the model metadata rather than on a happy-path payload,
    because re-tightening the annotation is exactly the change that
    would slip through a test that always passes a value.
    """
    from backend.api.admin import users as admin_users

    for model in (
        admin_users.AdminUserListItem,
        admin_users.AdminUserDetailResponse,
    ):
        assert not model.model_fields["telegram_id"].is_required(), model.__name__


# ---------------------------------------------------------------------------
# notifier_resolver — the second confirmed break
# ---------------------------------------------------------------------------


def _make_user(*, telegram_id=None, zalo_user_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        telegram_id=telegram_id,
        zalo_user_id=zalo_user_id,
    )


def test_resolve_targets_omits_telegram_for_zalo_only_user(monkeypatch):
    from backend.services import notifier_resolver

    class FakeOAClient:
        is_configured = True
        is_send_enabled = True

    monkeypatch.setattr(
        notifier_resolver, "get_zalo_oa_client", lambda: FakeOAClient()
    )

    targets = notifier_resolver.resolve_targets(
        _make_user(zalo_user_id="zuser-9")
    )

    assert [t.channel for t in targets] == ["zalo"]
    # The bug this replaces produced target_id == "None", which reads as
    # a valid chat_id everywhere downstream until Telegram rejects it.
    assert "None" not in [t.target_id for t in targets]


def test_resolve_targets_returns_empty_when_user_has_no_channel():
    from backend.services import notifier_resolver

    assert notifier_resolver.resolve_targets(_make_user()) == []


def test_resolve_targets_still_includes_telegram_when_present():
    """The nullable column must not cost the ordinary user anything."""
    from backend.services import notifier_resolver

    targets = notifier_resolver.resolve_targets(_make_user(telegram_id=12345))

    assert [t.channel for t in targets] == ["telegram"]
    assert targets[0].target_id == "12345"


# ---------------------------------------------------------------------------
# Proactive senders skip the Zalo-only user
# ---------------------------------------------------------------------------


class _CapturingSession:
    """Records the statements issued and answers with nothing."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, stmt):
        self.statements.append(str(stmt.compile()))
        return _EmptyResult()


class _EmptyResult:
    def all(self) -> list:
        return []

    def scalars(self) -> "_EmptyResult":
        return self

    def first(self):
        return None


@pytest.mark.asyncio
async def test_recurring_detection_query_excludes_telegramless_users():
    from backend.jobs import recurring_detection_job

    db = _CapturingSession()
    await recurring_detection_job._eligible_users(db)

    assert "users.telegram_id IS NOT NULL" in db.statements[0]


@pytest.mark.asyncio
async def test_price_alert_holder_query_excludes_telegramless_users():
    from backend.market_data.analytics import alerts

    db = _CapturingSession()
    await alerts._users_holding(db, "VNM")

    assert "users.telegram_id IS NOT NULL" in db.statements[0]


@pytest.mark.asyncio
async def test_reminder_scheduler_skips_zalo_only_user(monkeypatch):
    from backend.jobs import reminder_scheduler_job
    from backend.models.user import User

    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = None
    user.deleted_at = None

    class FakeSession:
        def __init__(self) -> None:
            self.commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, model, _pk):
            return user if model is User else None

        async def commit(self) -> None:
            self.commits += 1

        async def rollback(self) -> None:
            pass

    monkeypatch.setattr(
        reminder_scheduler_job, "get_session_factory", lambda: FakeSession
    )

    async def fake_load(_db):
        return {user.id: [object()]}

    sent: list = []

    async def fake_send(_db, _user, patterns):
        sent.append(patterns)

    monkeypatch.setattr(
        reminder_scheduler_job, "_load_due_patterns_by_user", fake_load
    )
    monkeypatch.setattr(reminder_scheduler_job, "_send_for_user", fake_send)

    await reminder_scheduler_job.run_reminder_scheduler(
        now=datetime(2026, 8, 3, 9, 0, tzinfo=reminder_scheduler_job.REMINDER_TIMEZONE)
    )

    assert sent == []


@pytest.mark.asyncio
async def test_reminder_scheduler_still_sends_to_telegram_user(monkeypatch):
    """Companion to the skip test — proves the guard is the reason."""
    from backend.jobs import reminder_scheduler_job
    from backend.models.user import User

    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 12345
    user.deleted_at = None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, model, _pk):
            return user if model is User else None

        async def commit(self) -> None:
            pass

        async def rollback(self) -> None:
            pass

    monkeypatch.setattr(
        reminder_scheduler_job, "get_session_factory", lambda: FakeSession
    )

    async def fake_load(_db):
        return {user.id: [object()]}

    sent: list = []

    async def fake_send(_db, _user, patterns):
        sent.append(patterns)

    monkeypatch.setattr(
        reminder_scheduler_job, "_load_due_patterns_by_user", fake_load
    )
    monkeypatch.setattr(reminder_scheduler_job, "_send_for_user", fake_send)

    await reminder_scheduler_job.run_reminder_scheduler(
        now=datetime(2026, 8, 3, 9, 0, tzinfo=reminder_scheduler_job.REMINDER_TIMEZONE)
    )

    assert len(sent) == 1


@pytest.mark.asyncio
async def test_morning_report_bails_before_building_anything(monkeypatch):
    from backend.services import morning_report_service
    from backend.models.user import User

    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = None

    async def explode(*_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("built a report for a user with nowhere to send it")

    monkeypatch.setattr(morning_report_service, "build_morning_report", explode)

    assert await morning_report_service.send_morning_report(None, user) is False


@pytest.mark.asyncio
async def test_feedback_prompt_scheduler_skips_zalo_only_user(monkeypatch):
    """No prompt, and — just as important — no quota spent."""
    from backend.feedback.services.prompt_scheduler import (
        FeedbackPrompt,
        PromptScheduler,
    )
    from backend.models.user import User

    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = None
    user.is_active = True

    class FakeSession:
        async def get(self, _model, _pk):
            return user

        async def execute(self, _stmt):  # pragma: no cover - must not run
            raise AssertionError("queried cooldown state for an unreachable user")

    # A prompt whose condition WOULD fire on day 7 — so if the guard
    # were removed the run would reach ``_metrics``, hit the session
    # above and fail loudly rather than passing for the wrong reason.
    # (Passing an explicit list also keeps ``content/`` out of the test:
    # an empty list is falsy and would fall back to ``load_prompts()``.)
    scheduler = PromptScheduler(
        prompts=[
            FeedbackPrompt(
                id="post_onboarding_day_7",
                trigger="post_onboarding_day_7",
                message="…",
                cta_button="Ừ",
                skip_button="Để sau",
                cooldown_days=90,
            )
        ]
    )
    sent = await scheduler.check_and_send_prompts(FakeSession(), user.id)

    assert sent == []


def test_user_model_allows_null_telegram_id():
    from backend.models.user import User

    column = User.__table__.c.telegram_id
    assert column.nullable is True
    # The unique index stays: Postgres treats NULLs as distinct, so
    # Zalo-only rows coexist while two real Telegram ids still collide.
    assert column.unique is True


def test_reminder_window_helper_unchanged():
    """Anchor for the two scheduler tests above — 09:00 is in-window."""
    from backend.jobs import reminder_scheduler_job

    assert reminder_scheduler_job._is_within_15_min(time(9, 0), time(9, 0))
