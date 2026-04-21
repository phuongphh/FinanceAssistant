import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers.transaction import send_transaction_confirmation
from backend.database import get_db
from backend.schemas.expense import (
    ExpenseCreate,
    ExpenseResponse,
    ExpenseSummary,
    ExpenseUpdate,
)
from backend.services import expense_service

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.post("", response_model=ExpenseResponse, status_code=201)
async def create_expense(
    data: ExpenseCreate,
    user_id: uuid.UUID = Query(..., description="User ID"),
    push_confirmation: bool = Query(
        False,
        description=(
            "Nếu true, backend sẽ push rich confirmation (kèm inline "
            "keyboard) tới Telegram chat của user. Mặc định false để "
            "tránh double-message khi caller (OpenClaw skill) đã tự gửi."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    expense = await expense_service.create_expense(db, user_id, data)
    if push_confirmation:
        await send_transaction_confirmation(db, expense)
    return expense


@router.get("", response_model=list[ExpenseResponse])
async def list_expenses(
    user_id: uuid.UUID = Query(...),
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    category: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await expense_service.list_expenses(
        db, user_id, month=month, category=category, limit=limit, offset=offset
    )


@router.get("/summary", response_model=ExpenseSummary)
async def get_summary(
    user_id: uuid.UUID = Query(...),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
):
    return await expense_service.get_expense_summary(db, user_id, month)


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    expense = await expense_service.get_expense(db, user_id, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.put("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: uuid.UUID,
    data: ExpenseUpdate,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    expense = await expense_service.update_expense(db, user_id, expense_id, data)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.delete("/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    deleted = await expense_service.delete_expense(db, user_id, expense_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Expense not found")
