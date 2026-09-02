"""Zalo → Telegram adoption — Phase 5.0 #1028.

``adopt_telegram_account`` decides whether a tapped invite may write a
``telegram_id`` onto an existing Zalo-first account. Every branch it can
take either prevents a duplicate account or refuses to move a binding, so
each one is pinned here.

Unit-only, no DB: ``FakeDB`` serves ``execute()`` from a queue in the
order the service issues its statements — token row, user row, then the
telegram_id-already-taken probe.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.user import User  # noqa: E402
from backend.models.zalo_link_token import ZaloLinkToken  # noqa: E402
from backend.services import zalo_linking_service  # noqa: E402


class _Scalars:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return list(self._rows)


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self) -> _Scalars:
        return _Scalars(self._value if isinstance(self._value, list) else [])


class FakeDB:
    """AsyncSession stand-in: ``execute()`` pops the next staged row."""

    def __init__(self, execute_queue: list[Any] | None = None) -> None:
        self._queue = list(execute_queue or [])
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.flush_count = 0

    async def execute(self, _stmt) -> _Result:
        return _Result(self._queue.pop(0) if self._queue else None)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def delete(self, obj) -> None:
        self.deleted.append(obj)

    async def flush(self) -> None:
        self.flush_count += 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user(**kwargs) -> User:
    user = User(**kwargs)
    user.id = kwargs.get("id") or uuid.uuid4()
    return user


def _token(
    user: User,
    *,
    purpose: str = zalo_linking_service.PURPOSE_TELEGRAM_ADOPT,
    used_at: datetime | None = None,
    expires_in: timedelta = timedelta(days=7),
) -> ZaloLinkToken:
    return ZaloLinkToken(
        token="adopt-token",
        user_id=user.id,
        purpose=purpose,
        expires_at=_now() + expires_in,
        used_at=used_at,
    )


@pytest.mark.asyncio
async def test_a_valid_invite_binds_telegram_to_the_zalo_account():
    user = _user(zalo_user_id="zalo-1")
    row = _token(user)
    db = FakeDB(execute_queue=[row, user, None])

    result = await zalo_linking_service.adopt_telegram_account(
        db, "adopt-token", 4242, telegram_handle="phuong", display_name="Phương"
    )

    assert result.status == "adopted"
    assert result.user is user
    assert user.telegram_id == 4242
    assert user.telegram_handle == "phuong"
    assert user.zalo_user_id == "zalo-1", "the Zalo side is kept, not replaced"
    assert row.used_at is not None
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_the_invite_never_overwrites_a_name_the_user_chose():
    user = _user(zalo_user_id="zalo-1", display_name="Phương", telegram_handle="cu")
    db = FakeDB(execute_queue=[_token(user), user, None])

    await zalo_linking_service.adopt_telegram_account(
        db, "adopt-token", 4242, telegram_handle="moi", display_name="Mới"
    )

    assert user.display_name == "Phương"
    assert user.telegram_handle == "cu"


@pytest.mark.asyncio
async def test_re_tapping_the_same_link_is_idempotent():
    """Double-tap is ordinary user behaviour, not an error to report."""
    user = _user(zalo_user_id="zalo-1", telegram_id=4242)
    row = _token(user, used_at=_now() - timedelta(minutes=5))
    db = FakeDB(execute_queue=[row, user])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 4242)

    assert result.status == "adopted"
    assert result.user is user
    assert db.flush_count == 0, "nothing changed, nothing to write"


@pytest.mark.asyncio
async def test_an_expired_link_still_honours_a_binding_it_already_made():
    """Expiry governs new bindings; one already made stays true."""
    user = _user(zalo_user_id="zalo-1", telegram_id=4242)
    row = _token(user, used_at=_now(), expires_in=timedelta(days=-1))
    db = FakeDB(execute_queue=[row, user])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 4242)

    assert result.status == "adopted"


@pytest.mark.asyncio
async def test_a_spent_link_is_refused_for_anybody_else():
    user = _user(zalo_user_id="zalo-1", telegram_id=4242)
    row = _token(user, used_at=_now() - timedelta(minutes=5))
    db = FakeDB(execute_queue=[row, user])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 777)

    assert result.status == "already_used"
    assert result.user is None
    assert user.telegram_id == 4242, "the original binding is untouched"


@pytest.mark.asyncio
async def test_an_expired_link_is_refused():
    user = _user(zalo_user_id="zalo-1")
    db = FakeDB(execute_queue=[_token(user, expires_in=timedelta(days=-1)), user])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 4242)

    assert result.status == "expired"
    assert user.telegram_id is None


@pytest.mark.asyncio
async def test_a_naive_expiry_is_read_as_utc_not_crashed_on():
    """Postgres hands back naive datetimes on some drivers."""
    user = _user(zalo_user_id="zalo-1")
    row = _token(user)
    row.expires_at = (_now() - timedelta(days=1)).replace(tzinfo=None)
    db = FakeDB(execute_queue=[row, user])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 4242)

    assert result.status == "expired"


@pytest.mark.asyncio
async def test_an_account_that_already_has_telegram_is_never_re_pointed():
    user = _user(zalo_user_id="zalo-1", telegram_id=111)
    db = FakeDB(execute_queue=[_token(user), user])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 4242)

    assert result.status == "conflict"
    assert user.telegram_id == 111


@pytest.mark.asyncio
async def test_a_telegram_id_owned_by_someone_else_is_never_stolen():
    """Merging two populated accounts is a different problem — refuse."""
    user = _user(zalo_user_id="zalo-1")
    db = FakeDB(execute_queue=[_token(user), user, uuid.uuid4()])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 4242)

    assert result.status == "conflict"
    assert user.telegram_id is None
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_a_link_token_cannot_be_spent_as_an_adoption_token():
    """The two flows share a table; ``purpose`` is what keeps them apart."""
    user = _user(zalo_user_id="zalo-1")
    row = _token(user, purpose=zalo_linking_service.PURPOSE_ZALO_LINK)
    db = FakeDB(execute_queue=[row, user])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 4242)

    assert result.status == "invalid"
    assert user.telegram_id is None


@pytest.mark.asyncio
async def test_an_adoption_token_cannot_be_spent_as_a_link_token():
    user = _user(zalo_user_id=None)
    row = _token(user)
    db = FakeDB(execute_queue=[row])

    result = await zalo_linking_service.redeem_link_token(db, "adopt-token", "zalo-9")

    assert result.status == "invalid"


@pytest.mark.asyncio
async def test_an_unknown_or_empty_token_is_invalid():
    db = FakeDB(execute_queue=[None])

    assert (
        await zalo_linking_service.adopt_telegram_account(db, "", 4242)
    ).status == "invalid"
    assert (
        await zalo_linking_service.adopt_telegram_account(db, "nope", 4242)
    ).status == "invalid"


@pytest.mark.asyncio
async def test_a_token_whose_owner_vanished_is_invalid_not_a_crash():
    user = _user(zalo_user_id="zalo-1")
    db = FakeDB(execute_queue=[_token(user), None])

    result = await zalo_linking_service.adopt_telegram_account(db, "adopt-token", 4242)

    assert result.status == "invalid"


@pytest.mark.asyncio
async def test_the_issued_invite_token_fits_a_telegram_start_payload():
    """``/start`` payloads are base64url and at most 64 chars; the column
    holds 16. A token that violates either would break the whole invite."""
    from backend.bot.handlers import zalo_adoption

    user = _user(zalo_user_id="zalo-1")
    db = FakeDB(execute_queue=[[], None])

    token = await zalo_linking_service.issue_telegram_adoption_token(db, user)
    payload = zalo_adoption.build_payload(token)

    assert 0 < len(token) <= 16
    assert len(payload) <= 64
    assert all(ch.isalnum() or ch in "_-" for ch in payload)
    assert zalo_adoption.adoption_token(payload) == token


@pytest.mark.asyncio
async def test_an_active_invite_is_reused_rather_than_stacked():
    """Re-offering must not leave several live credentials for one person."""
    user = _user(zalo_user_id="zalo-1")
    existing = _token(user)
    existing.token = "abc123"
    db = FakeDB(execute_queue=[[existing]])

    token = await zalo_linking_service.issue_telegram_adoption_token(db, user)

    assert token == "abc123"
    assert db.flush_count == 0
