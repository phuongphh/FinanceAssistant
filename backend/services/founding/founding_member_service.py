"""Founding-member service (Phase 4.1, Story C.4).

Owns the atomic sequence assignment that turns one of the 50 invite
codes into a "Founding Member #N" stamp on a user row. Race-safety is
critical: two users redeeming invite links in the same second must
get distinct sequences (1..50), never duplicates.

We use a Postgres advisory lock (single global integer key) rather
than ``SELECT ... FOR UPDATE`` on the users table because:

  1. No row to lock — sequence is computed from MAX().
  2. Advisory lock is cheap, scoped to the transaction, auto-released.
  3. Sequence assignment happens at most ~50 times, so contention is
     never a hot path; advisory is the simpler primitive.

The `compute_discount(user_id)` method is the API Phase 5.7 reads
when computing Pro paywall pricing — founding member → 0.5 off.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.invite_code import InviteCode
from backend.models.user import User

logger = logging.getLogger(__name__)


# Arbitrary 32-bit key for pg_advisory_xact_lock. Stable so all
# processes contend on the same slot. (Bot codename hash.)
_FOUNDING_LOCK_KEY = 0x4E7E_4E11  # ~"BeTien"


@dataclass(frozen=True)
class FoundingAssignment:
    sequence: int
    activated_at: datetime


class FoundingCapReachedError(RuntimeError):
    """50 seats filled — current invite redeems WITHOUT founding status."""


# Hard cap on founding cohort. Reads from a constant so Phase 5.7 can
# bump it via env if the soft-launch cohort grew.
FOUNDING_COHORT_CAP = 50


async def assign_sequence(db: AsyncSession, user: User) -> FoundingAssignment:
    """Atomically grant the next founding sequence to ``user``.

    Idempotent: if the user already has a sequence, returns it unchanged.
    Raises :class:`FoundingCapReachedError` if all 50 seats are taken.

    Caller commits at the worker boundary.
    """
    if user.founding_member_sequence is not None:
        # Already a founding member — return the stored assignment.
        return FoundingAssignment(
            sequence=user.founding_member_sequence,
            activated_at=user.founding_member_at or datetime.now(timezone.utc),
        )

    # Transaction-scoped advisory lock. Released on commit / rollback.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=_FOUNDING_LOCK_KEY)
    )

    # Re-check inside the lock (another tx may have promoted this user
    # between the load and the lock).
    refreshed = await db.get(User, user.id)
    if refreshed and refreshed.founding_member_sequence is not None:
        return FoundingAssignment(
            sequence=refreshed.founding_member_sequence,
            activated_at=refreshed.founding_member_at or datetime.now(timezone.utc),
        )

    max_seq = (
        await db.execute(select(func.max(User.founding_member_sequence)))
    ).scalar()
    next_seq = (max_seq or 0) + 1
    if next_seq > FOUNDING_COHORT_CAP:
        logger.warning(
            "Founding cohort cap reached — user %s redeems without founding",
            user.id,
        )
        raise FoundingCapReachedError()

    now = datetime.now(timezone.utc)
    user.is_founding_member = True
    user.founding_member_sequence = next_seq
    user.founding_member_at = now
    await db.flush()
    return FoundingAssignment(sequence=next_seq, activated_at=now)


async def is_founding(db: AsyncSession, user_id: uuid.UUID) -> bool:
    user = await db.get(User, user_id)
    return bool(user and user.is_founding_member)


def compute_discount(user: User) -> Decimal:
    """Return the lifetime discount multiplier for a Pro subscription.

    0.5 = 50% off (founding cohort), Decimal("0") = no discount.
    Phase 5.7 consumes this directly in the paywall pricing service.
    """
    return Decimal("0.5") if user.is_founding_member else Decimal("0")


async def find_invite(db: AsyncSession, token: str) -> InviteCode | None:
    """Return the invite row for ``token`` if it exists, else None."""
    stmt = select(InviteCode).where(InviteCode.token == token)
    return (await db.execute(stmt)).scalar_one_or_none()


async def mark_invite_redeemed(
    db: AsyncSession, invite: InviteCode, user: User
) -> None:
    invite.redeemed_by_user_id = user.id
    invite.redeemed_at = datetime.now(timezone.utc)
    if user.acquisition_source is None:
        user.acquisition_source = invite.source
    await db.flush()


async def list_founding_members(db: AsyncSession) -> list[User]:
    stmt = (
        select(User)
        .where(User.is_founding_member.is_(True))
        .order_by(User.founding_member_sequence.asc())
    )
    return list((await db.execute(stmt)).scalars().all())
