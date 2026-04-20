import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.models.expense import Expense
from backend.schemas.expense import ExpenseCreate, ExpenseUpdate


async def create_expense(
    db: AsyncSession, user_id: uuid.UUID, data: ExpenseCreate
) -> Expense:
    # Auto-categorize if category is needs_review and we have context
    category = data.category
    if category == "needs_review" and (data.merchant or data.note):
        from backend.services.llm_service import categorize_expense
        category = await categorize_expense(
            merchant=data.merchant, description=data.note,
            amount=data.amount, db=db,
        )

    month_key = data.expense_date.strftime("%Y-%m")
    expense = Expense(
        user_id=user_id,
        amount=data.amount,
        currency=data.currency,
        merchant=data.merchant,
        category=category,
        source=data.source,
        expense_date=data.expense_date,
        month_key=month_key,
        note=data.note,
        raw_data=data.raw_data,
        needs_review=data.needs_review,
        gmail_message_id=data.gmail_message_id,
    )
    db.add(expense)
    await db.flush()
    await db.refresh(expense)

    analytics.track(
        analytics.EventType.TRANSACTION_CREATED,
        user_id=user_id,
        properties={
            "source": data.source,
            "category": category,
            "needs_review": bool(data.needs_review),
            "auto_categorized": data.category == "needs_review",
        },
    )
    return expense


async def get_expense(
    db: AsyncSession, user_id: uuid.UUID, expense_id: uuid.UUID
) -> Expense | None:
    stmt = select(Expense).where(
        Expense.id == expense_id,
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_expenses(
    db: AsyncSession,
    user_id: uuid.UUID,
    month: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Expense]:
    stmt = select(Expense).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
    )
    if month:
        stmt = stmt.where(Expense.month_key == month)
    if category:
        stmt = stmt.where(Expense.category == category)
    stmt = stmt.order_by(Expense.expense_date.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_expense(
    db: AsyncSession,
    user_id: uuid.UUID,
    expense_id: uuid.UUID,
    data: ExpenseUpdate,
) -> Expense | None:
    expense = await get_expense(db, user_id, expense_id)
    if not expense:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(expense, field, value)
    await db.flush()
    await db.refresh(expense)
    return expense


async def delete_expense(
    db: AsyncSession, user_id: uuid.UUID, expense_id: uuid.UUID
) -> bool:
    expense = await get_expense(db, user_id, expense_id)
    if not expense:
        return False
    expense.deleted_at = datetime.utcnow()
    await db.flush()
    analytics.track(
        analytics.EventType.TRANSACTION_DELETED,
        user_id=user_id,
        properties={"via": "api", "source": expense.source},
    )
    return True


async def get_expense_summary(
    db: AsyncSession, user_id: uuid.UUID, month: str
) -> dict:
    stmt = (
        select(
            Expense.category,
            func.sum(Expense.amount).label("total"),
            func.count().label("count"),
        )
        .where(
            Expense.user_id == user_id,
            Expense.month_key == month,
            Expense.deleted_at.is_(None),
        )
        .group_by(Expense.category)
    )
    result = await db.execute(stmt)
    rows = result.all()

    by_category = {row.category: float(row.total) for row in rows}
    total = sum(by_category.values())
    count = sum(row.count for row in rows)

    return {
        "month_key": month,
        "total": total,
        "by_category": by_category,
        "count": count,
    }
