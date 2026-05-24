from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.models.asset import Asset
from backend.wealth.services import asset_service


def _months_paid(start_date: date) -> int:
    today = date.today()
    months = (today.year - start_date.year) * 12 + (today.month - start_date.month) + 1
    return max(1, months)


async def create_life_insurance(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    company_name: str,
    monthly_payment_date: int,
    monthly_amount: Decimal,
    contract_end_year: int,
    total_paid: Decimal | None = None,
    start_date: date | None = None,
) -> Asset:
    if not (1 <= int(monthly_payment_date) <= 31):
        raise ValueError("monthly_payment_date must be 1..31")
    if int(contract_end_year) < date.today().year:
        raise ValueError("contract_end_year must be current year or later")
    if Decimal(monthly_amount) <= 0:
        raise ValueError("monthly_amount must be positive")

    acquired = start_date or date.today()
    paid = Decimal(total_paid) if total_paid is not None else Decimal(monthly_amount) * _months_paid(acquired)
    return await asset_service.create_asset(
        db,
        user_id,
        asset_type="life_insurance",
        subtype="contract",
        name=company_name.strip(),
        initial_value=paid,
        current_value=paid,
        acquired_at=acquired,
        extra={
            "company_name": company_name.strip(),
            "monthly_payment_date": int(monthly_payment_date),
            "monthly_amount": float(monthly_amount),
            "contract_end_year": int(contract_end_year),
            "total_paid": float(paid),
        },
    )


async def get_life_insurance_list(db: AsyncSession, user_id: uuid.UUID) -> list[Asset]:
    return await asset_service.get_user_assets(db, user_id, asset_type="life_insurance")


async def get_life_insurance_by_id(db: AsyncSession, user_id: uuid.UUID, contract_id: uuid.UUID) -> Asset | None:
    asset = await asset_service.get_asset_by_id(db, user_id, contract_id)
    if asset is None or asset.asset_type != "life_insurance":
        return None
    return asset


async def update_life_insurance(
    db: AsyncSession,
    user_id: uuid.UUID,
    contract_id: uuid.UUID,
    **fields,
) -> Asset:
    asset = await get_life_insurance_by_id(db, user_id, contract_id)
    if asset is None:
        raise ValueError("Life insurance contract not found")

    extra = dict(asset.extra or {})
    for key in ["company_name", "monthly_payment_date", "monthly_amount", "contract_end_year", "total_paid"]:
        if key in fields and fields[key] is not None:
            extra[key] = fields[key]

    name = fields.get("company_name")
    if name is not None:
        asset.name = str(name).strip()
    if "total_paid" in fields and fields["total_paid"] is not None:
        asset.current_value = Decimal(fields["total_paid"])
        asset.initial_value = Decimal(fields["total_paid"])

    asset.extra = extra
    await db.flush()
    return asset


async def delete_life_insurance(db: AsyncSession, user_id: uuid.UUID, contract_id: uuid.UUID) -> Asset:
    return await asset_service.soft_delete(db, user_id, contract_id)
