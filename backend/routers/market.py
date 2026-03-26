import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.market import MarketSnapshotResponse
from backend.services.market_service import (
    fetch_daily_snapshot,
    generate_investment_advice,
    get_asset_history,
    get_latest_snapshots,
    save_snapshots,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/snapshot", response_model=list[MarketSnapshotResponse])
async def get_snapshot(db: AsyncSession = Depends(get_db)):
    snapshots = await get_latest_snapshots(db)
    if not snapshots:
        # Fetch fresh data
        raw = await fetch_daily_snapshot()
        snapshots = await save_snapshots(db, raw)
    return snapshots


@router.get("/history", response_model=list[MarketSnapshotResponse])
async def get_history(
    asset: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    return await get_asset_history(db, asset, days)


@router.post("/advice")
async def get_advice(
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    advice = await generate_investment_advice(db, user_id)
    return {"data": {"advice": advice}, "error": None}
