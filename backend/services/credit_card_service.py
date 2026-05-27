from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.credit_card import CreditCard
from backend.schemas.credit_card import CreditCardCreate, CreditCardUpdate


async def create_credit_card(
    db: AsyncSession, user_id: uuid.UUID, data: CreditCardCreate
) -> CreditCard:
    """Create a credit card for a user with case-insensitive bank-name uniqueness."""
    normalized_name = data.bank_name.strip()
    existing = await db.execute(
        select(CreditCard).where(
            CreditCard.user_id == user_id,
            func.lower(CreditCard.bank_name) == normalized_name.lower(),
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
    """Return all credit cards of a user, newest first."""
    rows = await db.execute(
        select(CreditCard)
        .where(CreditCard.user_id == user_id)
        .order_by(CreditCard.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_credit_card(
    db: AsyncSession, user_id: uuid.UUID, card_id: uuid.UUID
) -> CreditCard | None:
    """Return a single credit card by id if it belongs to the user."""
    return (
        await db.execute(
            select(CreditCard).where(
                CreditCard.id == card_id,
                CreditCard.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def delete_credit_card(
    db: AsyncSession, user_id: uuid.UUID, card_id: uuid.UUID
) -> CreditCard | None:
    card = await get_credit_card(db, user_id, card_id)
    if card is None:
        return None
    await db.delete(card)
    await db.flush()
    return card
