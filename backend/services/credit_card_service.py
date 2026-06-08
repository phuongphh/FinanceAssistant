from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.credit_card import CreditCard
from backend.schemas.credit_card import CreditCardCreate, CreditCardUpdate


async def create_credit_card(
    db: AsyncSession, user_id: uuid.UUID, data: CreditCardCreate
) -> CreditCard:
    """Create a credit card for a user with case-insensitive bank-name uniqueness.

    Soft-deleted rows are excluded from the duplicate check, so a user
    who removed a card can re-add the same bank later.
    """
    normalized_name = data.bank_name.strip()
    existing = await db.execute(
        select(CreditCard).where(
            CreditCard.user_id == user_id,
            func.lower(CreditCard.bank_name) == normalized_name.lower(),
            CreditCard.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Tên ngân hàng đã tồn tại")
    card = CreditCard(
        user_id=user_id,
        bank_name=normalized_name,
        credit_limit=Decimal(str(data.credit_limit)),
        closing_date=data.closing_date,
        debt_balance=Decimal(str(data.debt_balance)),
    )
    db.add(card)
    await db.flush()
    await db.refresh(card)
    return card


async def list_credit_cards(db: AsyncSession, user_id: uuid.UUID) -> list[CreditCard]:
    """Return all live credit cards of a user, newest first.

    Soft-deleted rows are filtered out — they only stay around so
    historical expenses referencing ``source_credit_card_id`` can still
    resolve the bank name on the confirmation card.
    """
    rows = await db.execute(
        select(CreditCard)
        .where(
            CreditCard.user_id == user_id,
            CreditCard.deleted_at.is_(None),
        )
        .order_by(CreditCard.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_credit_card(
    db: AsyncSession, user_id: uuid.UUID, card_id: uuid.UUID
) -> CreditCard | None:
    """Return a single live credit card by id if it belongs to the user."""
    return (
        await db.execute(
            select(CreditCard).where(
                CreditCard.id == card_id,
                CreditCard.user_id == user_id,
                CreditCard.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def delete_credit_card(
    db: AsyncSession, user_id: uuid.UUID, card_id: uuid.UUID
) -> CreditCard | None:
    """Soft-delete the card.

    The row is kept so historical expenses' ``source_credit_card_id``
    FK still resolves; ``deleted_at`` hides it from the menu, NLU
    matcher, and profile picker. Returns the deleted card or ``None``
    if no live card matched.
    """
    card = await get_credit_card(db, user_id, card_id)
    if card is None:
        return None
    card.deleted_at = datetime.utcnow()
    await db.flush()
    return card
