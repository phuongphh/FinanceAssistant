"""Zalo linking — token issuance + redemption.

Phase 4B Epic 4 (Story P4B-S23).

Two-step pairing flow:

1. User runs ``/link_zalo`` in Telegram → :func:`issue_link_token`
   generates a 6-char random code ``BT-XXXXXX``, persists it with a
   10-minute TTL, and returns it to the Telegram handler for display.
2. User pastes the code into the Zalo OA chat → the Zalo webhook
   calls :func:`redeem_link_token`, which looks the token up, marks
   it used, and writes ``users.zalo_user_id``.

Tokens are short, single-use, and time-boxed so a leaked or shared
code can't grant indefinite linking access. ``BT-`` prefix + base32
alphabet (no I/O/0/1) gives ~33^6 = 1.3B codes — collision risk in a
10-minute window is negligible.

Phase 5.1 #4.3 adds the other direction: a person can now arrive from
the Zalo OA having never touched Telegram, so this module also owns
:func:`get_or_create_zalo_user` (the account that pairing used to
assume already existed) and the markers for the one-time "come to
Telegram too" invitation shown at the end of Zalo onboarding.

Layer contract:
- Service NEVER calls ``db.commit()``. Caller (router/handler) owns
  the transaction boundary.
- All DB writes are ``flush``-only.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.models.zalo_link_token import ZaloLinkToken

logger = logging.getLogger(__name__)

# Token TTL — Story #440 spec: 10 minutes.
TOKEN_TTL_MINUTES: Final[int] = 10

# Token alphabet: Crockford base32 minus I/O/L/U for legibility.
# Users will be typing the code on a Zalo mobile keyboard, so we drop
# easily-confused glyphs.
_TOKEN_ALPHABET: Final[str] = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
_TOKEN_BODY_LENGTH: Final[int] = 6
_TOKEN_PREFIX: Final[str] = "BT-"

# Max active (unused, unexpired) tokens per user — caps abuse where
# someone spams /link_zalo to inflate the table. New issuance past
# this limit reuses the most recent valid token.
_MAX_ACTIVE_TOKENS_PER_USER: Final[int] = 3


@dataclass(frozen=True)
class LinkRedemption:
    """Result of redeeming a token via the Zalo webhook."""

    status: str  # "linked" | "invalid" | "expired" | "already_used" | "user_relinked"
    user_id: UUID | None = None
    previous_zalo_user_id: str | None = None


def _generate_token_body() -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_BODY_LENGTH))


def _now() -> datetime:
    # ``datetime.utcnow`` is naive; we want timezone-aware to match the
    # ``DateTime(timezone=True)`` columns and avoid Postgres coercing
    # to local time on comparison.
    return datetime.now(tz=timezone.utc)


async def issue_link_token(db: AsyncSession, user: User) -> str:
    """Issue (or re-use) a Zalo linking token for ``user``.

    If the user already has an unused, unexpired token we return that
    so the spec's "Mã chỉ dùng được 1 lần" guarantee holds (a user
    spamming the command shouldn't quietly invalidate the token they
    already pasted into Zalo).
    """
    now = _now()
    existing_q = await db.execute(
        select(ZaloLinkToken)
        .where(ZaloLinkToken.user_id == user.id)
        .where(ZaloLinkToken.used_at.is_(None))
        .where(ZaloLinkToken.expires_at > now)
        .order_by(ZaloLinkToken.created_at.desc())
    )
    active = existing_q.scalars().all()
    if active:
        # Prune older surplus tokens (keep latest, the one we return)
        # to avoid token-table bloat on noisy users.
        for stale in active[1:]:
            await db.delete(stale)
        return active[0].token

    expires = now + timedelta(minutes=TOKEN_TTL_MINUTES)
    # Retry on the (extremely unlikely) PK collision — secrets gives
    # cryptographic randomness so this loop almost always exits in 1
    # iteration. Bounded to avoid pathological infinite loops in tests.
    for _ in range(5):
        token = f"{_TOKEN_PREFIX}{_generate_token_body()}"
        exists_q = await db.execute(
            select(ZaloLinkToken.token).where(ZaloLinkToken.token == token)
        )
        if exists_q.scalar_one_or_none() is None:
            break
    else:
        # Defensive — should never trigger with 30-char alphabet × 6.
        raise RuntimeError("ZaloLinkToken: unable to find unique token after 5 tries")

    db.add(
        ZaloLinkToken(
            token=token,
            user_id=user.id,
            expires_at=expires,
            created_at=now,
        )
    )
    await db.flush()
    return token


def normalize_token_input(text: str) -> str | None:
    """Pull a ``BT-XXXXXX`` token out of free-form Zalo message text.

    Users will paste the code with stray whitespace / line breaks /
    emoji from the linking instructions. We do case-insensitive prefix
    match and uppercase the body before lookup so the alphabet stays
    canonical.
    """
    if not text:
        return None
    # Find the prefix anywhere in the message — users sometimes type
    # "mã của tôi: BT-ABC123 nhé".
    upper = text.upper()
    idx = upper.find(_TOKEN_PREFIX)
    if idx < 0:
        return None
    candidate = upper[idx : idx + len(_TOKEN_PREFIX) + _TOKEN_BODY_LENGTH]
    if len(candidate) < len(_TOKEN_PREFIX) + _TOKEN_BODY_LENGTH:
        return None
    body = candidate[len(_TOKEN_PREFIX) :]
    if not all(c in _TOKEN_ALPHABET for c in body):
        return None
    return candidate


async def redeem_link_token(
    db: AsyncSession, token: str, zalo_user_id: str
) -> LinkRedemption:
    """Bind a Zalo user_id to the user that owns ``token``.

    Idempotent on the (user, zalo_user_id) pair — re-running the same
    token after success returns ``already_used``; a different Zalo
    account presenting the same already-used token is rejected.
    """
    if not token or not zalo_user_id:
        return LinkRedemption(status="invalid")

    row_q = await db.execute(select(ZaloLinkToken).where(ZaloLinkToken.token == token))
    row: ZaloLinkToken | None = row_q.scalar_one_or_none()
    if row is None:
        return LinkRedemption(status="invalid")

    now = _now()
    if row.used_at is not None:
        return LinkRedemption(status="already_used", user_id=row.user_id)

    # Compare in UTC. SQLAlchemy returns timezone-aware datetimes when
    # the column is ``DateTime(timezone=True)``; if we ever got a
    # naive value (sqlite in tests), promote it.
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        return LinkRedemption(status="expired", user_id=row.user_id)

    user_q = await db.execute(select(User).where(User.id == row.user_id))
    user: User | None = user_q.scalar_one_or_none()
    if user is None:
        # Should not happen with FK constraint, but defensive.
        return LinkRedemption(status="invalid")

    # If another user has already linked this Zalo account, reject.
    conflict_q = await db.execute(
        select(User.id)
        .where(User.zalo_user_id == zalo_user_id)
        .where(User.id != user.id)
    )
    if conflict_q.scalar_one_or_none() is not None:
        logger.warning(
            "Zalo redemption blocked: zalo_user_id=%s already linked to a "
            "different user",
            zalo_user_id,
        )
        return LinkRedemption(status="invalid")

    previous = user.zalo_user_id
    user.zalo_user_id = zalo_user_id
    row.used_at = now
    await db.flush()

    status = "user_relinked" if previous and previous != zalo_user_id else "linked"
    return LinkRedemption(
        status=status,
        user_id=user.id,
        previous_zalo_user_id=previous,
    )


async def get_linked_user(db: AsyncSession, zalo_user_id: str) -> User | None:
    """Return the user bound to ``zalo_user_id``, or ``None`` if unlinked.

    Lives here rather than in the handler so the "who is this Zalo
    sender?" question has one implementation — the handler must not
    issue raw queries (layer contract), and the inbound path asks this
    on every non-token message.
    """
    if not zalo_user_id:
        return None
    result = await db.execute(select(User).where(User.zalo_user_id == zalo_user_id))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    """Load a user by primary key.

    Needed by the inbound handler to reach the Telegram side of a fresh
    link (the redemption result carries only the id). Kept next to
    :func:`get_linked_user` for the same reason: handlers don't query.
    """
    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_or_create_zalo_user(
    db: AsyncSession, zalo_user_id: str, *, display_name: str | None = None
) -> tuple[User, bool]:
    """Return ``(user, created)`` for a Zalo sender with no link yet.

    Until 5.1 every account started on Telegram and the Zalo side only
    ever *found* users. #4.3 makes the OA a signup channel, so somebody
    has to mint the row — and it belongs here rather than in the handler
    because handlers don't write to the database.

    The created user has ``telegram_id`` NULL (see the #4.2 migration:
    there is no honest placeholder) and no ``display_name`` unless the
    caller passes one — onboarding asks for the name in its first step,
    and a name we made up would be worse than the "bạn" fallback.
    """
    if not zalo_user_id:
        raise ValueError("zalo_user_id is required to create a Zalo-first user")

    existing = await get_linked_user(db, zalo_user_id)
    if existing is not None:
        return existing, False

    user = User(zalo_user_id=zalo_user_id, display_name=display_name)
    db.add(user)
    # TRANSACTION_OWNED_BY_CALLER — the worker commits at the boundary.
    # flush() populates user.id from the DB default without ending the tx,
    # which onboarding needs immediately to open its session row.
    await db.flush()
    await db.refresh(user)
    logger.info("Created Zalo-first user %s from zalo_user_id", user.id)
    return user, True


# Recorded in ``users.zalo_telegram_invite_response``. Only the refusal
# has a value: accepting happens by opening a Telegram link, which never
# comes back to Zalo, and ignoring is represented by NULL. See the model.
INVITE_RESPONSE_DECLINED: Final[str] = "declined"


def telegram_invite_pending(user: User) -> bool:
    """True when the one-time Telegram invitation still owes a send.

    Pure predicate so the handler can ask without touching the DB, and
    so the "at most once" rule has exactly one definition. The gate is
    the timestamp alone: an invitation the user simply ignored has still
    been *shown*, and #4.3 says we do not ask twice.

    A user who already has a Telegram id has nothing to be invited to.
    """
    if user is None:
        return False
    if user.telegram_id is not None:
        return False
    return user.zalo_telegram_invite_at is None


async def mark_telegram_invite_shown(db: AsyncSession, user: User) -> None:
    """Stamp the invitation as sent. Idempotent — a second call is a no-op
    so a retried send can never reset the once-only gate."""
    if user.zalo_telegram_invite_at is not None:
        return
    user.zalo_telegram_invite_at = _now()
    await db.flush()


async def record_telegram_invite_response(
    db: AsyncSession, user: User, response: str
) -> None:
    """Remember what the user answered ("declined").

    Kept separate from :func:`mark_telegram_invite_shown` because the
    answer is optional: silence is a valid outcome and must not look
    like a decline to whoever reads this row later.
    """
    user.zalo_telegram_invite_response = response
    if user.zalo_telegram_invite_at is None:
        # Defensive: an answer implies the invite went out. Without this
        # a mis-ordered call would leave the gate open and re-invite.
        user.zalo_telegram_invite_at = _now()
    await db.flush()


async def unlink_user(db: AsyncSession, user: User) -> bool:
    """Clear the Zalo binding. Returns True if the user was linked
    before this call (so the handler can show a different message for
    the no-op case)."""
    if not user.zalo_user_id:
        return False
    user.zalo_user_id = None
    await db.flush()
    return True
