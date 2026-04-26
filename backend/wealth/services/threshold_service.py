"""Income-based expense threshold computation.

Phase 3A storytelling captures only the giao dịch that actually matter
to a user — and "matter" scales with their monthly income. Someone on
12tr/month feels a 200k coffee run; someone on 80tr/month doesn't.

This service derives two thresholds:

- ``micro``: anything below it is small enough to ignore. Storytelling
  drops these explicitly so the LLM doesn't waste tokens (and the user
  isn't asked to re-confirm a snack).
- ``major``: anything above it is a "stop and pay attention" event —
  morning briefing surfaces these proactively in later phases.

Brackets follow ``docs/current/phase-3a-detailed.md § 3.1``. Boundaries
are inclusive on the low side (``income == 15tr`` falls into the
15-30tr bucket) so a user who exactly hits a band's floor sees the
larger thresholds, never the smaller ones.

Service flushes only — caller (router/worker) owns the transaction
boundary and calls ``session.commit()``.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.wealth.models.income_stream import IncomeStream

# Defaults when income is missing/zero — match users.expense_threshold_*
# DB defaults so a brand-new user with no income setup still gets
# sensible storytelling behaviour.
DEFAULT_MICRO = Decimal("200_000")
DEFAULT_MAJOR = Decimal("2_000_000")


def compute_thresholds(
    monthly_income: Decimal | int | float | None,
) -> tuple[Decimal, Decimal]:
    """Return ``(micro, major)`` for the income bracket.

    Brackets:

    - ``< 15tr``           → (100k,  1tr)
    - ``15tr - 30tr``      → (200k,  2tr)
    - ``30tr - 60tr``      → (300k,  3tr)
    - ``>= 60tr``          → (500k,  5tr)

    ``None`` and ``0`` are explicitly bucketed to defaults — we don't
    want a user who hasn't entered income yet to see the most
    aggressive (lowest) thresholds, because the LLM would surface
    every coffee run.
    """
    if monthly_income is None:
        return (DEFAULT_MICRO, DEFAULT_MAJOR)

    try:
        income = Decimal(monthly_income)
    except Exception:
        return (DEFAULT_MICRO, DEFAULT_MAJOR)

    if income <= 0:
        return (DEFAULT_MICRO, DEFAULT_MAJOR)

    if income < Decimal("15_000_000"):
        return (Decimal("100_000"), Decimal("1_000_000"))
    if income < Decimal("30_000_000"):
        return (Decimal("200_000"), Decimal("2_000_000"))
    if income < Decimal("60_000_000"):
        return (Decimal("300_000"), Decimal("3_000_000"))
    return (Decimal("500_000"), Decimal("5_000_000"))


async def get_monthly_income(
    db: AsyncSession, user_id: uuid.UUID
) -> Decimal:
    """Sum ``amount_monthly`` across the user's active income streams.

    Falls back to the legacy ``users.monthly_income`` field if no
    streams exist — this keeps users who set up income before the
    income_streams table arrived working without a backfill.
    """
    stmt = select(func.coalesce(func.sum(IncomeStream.amount_monthly), 0)).where(
        IncomeStream.user_id == user_id,
        IncomeStream.is_active.is_(True),
    )
    streams_total = (await db.execute(stmt)).scalar_one()
    streams_total = Decimal(streams_total or 0)
    if streams_total > 0:
        return streams_total

    user = await db.get(User, user_id)
    if user is None or user.monthly_income is None:
        return Decimal(0)
    return Decimal(user.monthly_income)


async def update_user_thresholds(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    """Recompute and persist thresholds based on current income streams.

    Call after any income_streams mutation. No-op if the user is
    missing — caller can verify existence separately. Returns the
    written ``(micro, major)`` tuple so handlers can echo it back to
    the user without a second read.
    """
    user = await db.get(User, user_id)
    if user is None:
        return (DEFAULT_MICRO, DEFAULT_MAJOR)

    income = await get_monthly_income(db, user_id)
    micro, major = compute_thresholds(income)

    # ``users.expense_threshold_*`` are Integer columns — store as int
    # to keep type-roundtripping clean. Decimals always represent
    # whole VND amounts here so the cast is lossless.
    user.expense_threshold_micro = int(micro)
    user.expense_threshold_major = int(major)

    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()
    return (micro, major)
