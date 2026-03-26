import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.report import MonthlyReport
from backend.schemas.report import ReportResponse
from backend.services.report_service import generate_monthly_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly", response_model=ReportResponse)
async def get_monthly_report(
    user_id: uuid.UUID = Query(...),
    month: str = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
):
    if not month:
        month = date.today().strftime("%Y-%m")

    # Try to find existing report
    stmt = select(MonthlyReport).where(
        MonthlyReport.user_id == user_id,
        MonthlyReport.month_key == month,
    )
    report = (await db.execute(stmt)).scalar_one_or_none()

    if not report:
        # Auto-generate
        report = await generate_monthly_report(db, user_id, month)

    return report


@router.get("/history", response_model=list[ReportResponse])
async def get_report_history(
    user_id: uuid.UUID = Query(...),
    limit: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MonthlyReport)
        .where(MonthlyReport.user_id == user_id)
        .order_by(MonthlyReport.month_key.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/generate", response_model=ReportResponse)
async def force_generate_report(
    user_id: uuid.UUID = Query(...),
    month: str = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
):
    if not month:
        month = date.today().strftime("%Y-%m")
    report = await generate_monthly_report(db, user_id, month)
    return report
