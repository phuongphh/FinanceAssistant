import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.report import MonthlyReport
from backend.models.user import User
from backend.schemas.report import ReportResponse
from backend.services.morning_report_service import build_morning_report, send_morning_report
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


@router.post("/morning-report")
async def trigger_morning_report(
    user_id: uuid.UUID = Query(...),
    send_telegram: bool = Query(True, description="Send via Telegram"),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger the morning portfolio report for a user."""
    from fastapi.responses import Response
    from sqlalchemy import select as sa_select

    user = (
        await db.execute(
            sa_select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    chart_bytes, text_summary, has_assets = await build_morning_report(db, user_id)

    if send_telegram and user.telegram_id:
        await send_morning_report(db, user)
        return {"data": {"sent": True, "has_assets": has_assets}, "error": None}

    if chart_bytes:
        return Response(content=chart_bytes, media_type="image/png")

    return {"data": {"sent": False, "has_assets": False, "message": "No assets"}, "error": None}
