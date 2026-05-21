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
        closing_date=data.closing_date,
        debt_balance=Decimal(str(data.debt_balance)),
    )
    db.add(card)
    await db.flush()
    await db.refresh(card)
    return card


async def list_credit_cards(db: AsyncSession, user_id: uuid.UUID) -> list[CreditCard]:
    rows = await db.execute(
        select(CreditCard)
        .where(CreditCard.user_id == user_id)
        .order_by(CreditCard.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_credit_card(
    db: AsyncSession, user_id: uuid.UUID, card_id: uuid.UUID
) -> CreditCard | None:
    return (
        await db.execute(
            select(CreditCard).where(
                CreditCard.id == card_id,
                CreditCard.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

