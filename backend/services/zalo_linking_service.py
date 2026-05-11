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
    return "".join(
        secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_BODY_LENGTH)
    )


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

    row_q = await db.execute(
        select(ZaloLinkToken).where(ZaloLinkToken.token == token)
    )
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


async def unlink_user(db: AsyncSession, user: User) -> bool:
    """Clear the Zalo binding. Returns True if the user was linked
    before this call (so the handler can show a different message for
    the no-op case)."""
    if not user.zalo_user_id:
        return False
    user.zalo_user_id = None
    await db.flush()
    return True
