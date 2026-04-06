import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.portfolio import (
    PortfolioAssetCreate,
    PortfolioAssetResponse,
    PortfolioAssetUpdate,
    PortfolioSummary,
)
from backend.services import portfolio_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/assets", response_model=PortfolioAssetResponse, status_code=201)
async def create_asset(
    data: PortfolioAssetCreate,
    user_id: uuid.UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    asset = await portfolio_service.create_asset(db, user_id, data)
    return portfolio_service.enrich_asset_response(asset)


@router.get("/assets", response_model=list[PortfolioAssetResponse])
async def list_assets(
    user_id: uuid.UUID = Query(...),
    asset_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    assets = await portfolio_service.list_assets(
        db, user_id, asset_type=asset_type, limit=limit, offset=offset
    )
    return [portfolio_service.enrich_asset_response(a) for a in assets]


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await portfolio_service.get_portfolio_summary(db, user_id)


@router.get("/assets/{asset_id}", response_model=PortfolioAssetResponse)
async def get_asset(
    asset_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    asset = await portfolio_service.get_asset(db, user_id, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return portfolio_service.enrich_asset_response(asset)


@router.put("/assets/{asset_id}", response_model=PortfolioAssetResponse)
async def update_asset(
    asset_id: uuid.UUID,
    data: PortfolioAssetUpdate,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    asset = await portfolio_service.update_asset(db, user_id, asset_id, data)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return portfolio_service.enrich_asset_response(asset)


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    deleted = await portfolio_service.delete_asset(db, user_id, asset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Asset not found")
