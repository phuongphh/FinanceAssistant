import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.income import (
    IncomeRecordCreate,
    IncomeRecordResponse,
    IncomeRecordUpdate,
    IncomeSummary,
)
from backend.services import income_service

router = APIRouter(prefix="/income", tags=["income"])


@router.post("", response_model=IncomeRecordResponse, status_code=201)
async def create_income(
    data: IncomeRecordCreate,
    user_id: uuid.UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    return await income_service.create_income(db, user_id, data)


@router.get("", response_model=list[IncomeRecordResponse])
async def list_incomes(
    user_id: uuid.UUID = Query(...),
    income_type: str | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await income_service.list_incomes(
        db, user_id,
        income_type=income_type,
        period_from=period_from,
        period_to=period_to,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=IncomeSummary)
async def get_income_summary(
    user_id: uuid.UUID = Query(...),
    period_from: date = Query(..., description="Start date (first day of month)"),
    period_to: date = Query(..., description="End date (first day of month)"),
    db: AsyncSession = Depends(get_db),
):
    return await income_service.get_income_summary(db, user_id, period_from, period_to)


@router.get("/{income_id}", response_model=IncomeRecordResponse)
async def get_income(
    income_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    record = await income_service.get_income(db, user_id, income_id)
    if not record:
        raise HTTPException(status_code=404, detail="Income record not found")
    return record


@router.put("/{income_id}", response_model=IncomeRecordResponse)
async def update_income(
    income_id: uuid.UUID,
    data: IncomeRecordUpdate,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    record = await income_service.update_income(db, user_id, income_id, data)
    if not record:
        raise HTTPException(status_code=404, detail="Income record not found")
    return record


@router.delete("/{income_id}", status_code=204)
async def delete_income(
    income_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    deleted = await income_service.delete_income(db, user_id, income_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Income record not found")
