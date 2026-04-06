import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.income_record import IncomeRecord
from backend.schemas.income import IncomeRecordCreate, IncomeRecordUpdate


async def create_income(
    db: AsyncSession, user_id: uuid.UUID, data: IncomeRecordCreate
) -> IncomeRecord:
    record = IncomeRecord(
        user_id=user_id,
        income_type=data.income_type,
        source=data.source,
        asset_id=data.asset_id,
        amount=data.amount,
        period=data.period,
        note=data.note,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_income(
    db: AsyncSession, user_id: uuid.UUID, income_id: uuid.UUID
) -> IncomeRecord | None:
    stmt = select(IncomeRecord).where(
        IncomeRecord.id == income_id,
        IncomeRecord.user_id == user_id,
        IncomeRecord.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_incomes(
    db: AsyncSession,
    user_id: uuid.UUID,
    income_type: str | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[IncomeRecord]:
    stmt = select(IncomeRecord).where(
        IncomeRecord.user_id == user_id,
        IncomeRecord.deleted_at.is_(None),
    )
    if income_type:
        stmt = stmt.where(IncomeRecord.income_type == income_type)
    if period_from:
        stmt = stmt.where(IncomeRecord.period >= period_from)
    if period_to:
        stmt = stmt.where(IncomeRecord.period <= period_to)
    stmt = stmt.order_by(IncomeRecord.period.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_income(
    db: AsyncSession,
    user_id: uuid.UUID,
    income_id: uuid.UUID,
    data: IncomeRecordUpdate,
) -> IncomeRecord | None:
    record = await get_income(db, user_id, income_id)
    if not record:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)
    await db.flush()
    await db.refresh(record)
    return record


async def delete_income(
    db: AsyncSession, user_id: uuid.UUID, income_id: uuid.UUID
) -> bool:
    record = await get_income(db, user_id, income_id)
    if not record:
        return False
    record.deleted_at = datetime.utcnow()
    await db.flush()
    return True


async def get_income_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
    period_from: date,
    period_to: date,
) -> dict:
    stmt = (
        select(
            IncomeRecord.income_type,
            IncomeRecord.source,
            func.sum(IncomeRecord.amount).label("total"),
        )
        .where(
            IncomeRecord.user_id == user_id,
            IncomeRecord.period >= period_from,
            IncomeRecord.period <= period_to,
            IncomeRecord.deleted_at.is_(None),
        )
        .group_by(IncomeRecord.income_type, IncomeRecord.source)
    )
    result = await db.execute(stmt)
    rows = result.all()

    total_active = 0.0
    total_passive = 0.0
    by_source: dict[str, float] = {}

    for row in rows:
        amount = float(row.total)
        if row.income_type == "active":
            total_active += amount
        else:
            total_passive += amount
        by_source[row.source] = by_source.get(row.source, 0.0) + amount

    total = total_active + total_passive
    passive_ratio = round((total_passive / total) * 100, 2) if total > 0 else None

    return {
        "period_start": period_from,
        "period_end": period_to,
        "total_active": total_active,
        "total_passive": total_passive,
        "total": total,
        "passive_ratio": passive_ratio,
        "by_source": by_source,
    }
