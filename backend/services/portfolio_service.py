import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio_asset import PortfolioAsset
from backend.schemas.portfolio import PortfolioAssetCreate, PortfolioAssetUpdate


async def create_asset(
    db: AsyncSession, user_id: uuid.UUID, data: PortfolioAssetCreate
) -> PortfolioAsset:
    asset = PortfolioAsset(
        user_id=user_id,
        asset_type=data.asset_type,
        name=data.name,
        quantity=data.quantity,
        purchase_price=data.purchase_price,
        current_price=data.current_price,
        metadata_=data.metadata,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


async def get_asset(
    db: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID
) -> PortfolioAsset | None:
    stmt = select(PortfolioAsset).where(
        PortfolioAsset.id == asset_id,
        PortfolioAsset.user_id == user_id,
        PortfolioAsset.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_assets(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[PortfolioAsset]:
    stmt = select(PortfolioAsset).where(
        PortfolioAsset.user_id == user_id,
        PortfolioAsset.deleted_at.is_(None),
    )
    if asset_type:
        stmt = stmt.where(PortfolioAsset.asset_type == asset_type)
    stmt = stmt.order_by(PortfolioAsset.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    data: PortfolioAssetUpdate,
) -> PortfolioAsset | None:
    asset = await get_asset(db, user_id, asset_id)
    if not asset:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "metadata":
            setattr(asset, "metadata_", value)
        else:
            setattr(asset, field, value)
    await db.flush()
    await db.refresh(asset)
    return asset


async def delete_asset(
    db: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID
) -> bool:
    asset = await get_asset(db, user_id, asset_id)
    if not asset:
        return False
    asset.deleted_at = datetime.utcnow()
    await db.flush()
    return True


def _compute_asset_fields(asset: PortfolioAsset) -> dict:
    """Compute P&L and market value for an asset."""
    market_value = None
    unrealized_pnl = None
    unrealized_pnl_pct = None

    quantity = float(asset.quantity) if asset.quantity is not None else None
    current_price = float(asset.current_price) if asset.current_price is not None else None
    purchase_price = float(asset.purchase_price) if asset.purchase_price is not None else None

    if quantity is not None and current_price is not None:
        market_value = quantity * current_price

    if market_value is not None and purchase_price is not None and quantity is not None:
        cost = quantity * purchase_price
        unrealized_pnl = market_value - cost
        if cost > 0:
            unrealized_pnl_pct = round((unrealized_pnl / cost) * 100, 2)

    return {
        "market_value": market_value,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
    }


def enrich_asset_response(asset: PortfolioAsset) -> dict:
    """Convert asset to response dict with computed P&L fields."""
    data = {
        "id": asset.id,
        "user_id": asset.user_id,
        "asset_type": asset.asset_type,
        "name": asset.name,
        "quantity": float(asset.quantity) if asset.quantity is not None else None,
        "purchase_price": float(asset.purchase_price) if asset.purchase_price is not None else None,
        "current_price": float(asset.current_price) if asset.current_price is not None else None,
        "metadata": asset.metadata_,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }
    data.update(_compute_asset_fields(asset))
    return data


async def get_portfolio_summary(
    db: AsyncSession, user_id: uuid.UUID
) -> dict:
    assets = await list_assets(db, user_id, limit=500)

    total_market_value = 0.0
    total_cost = 0.0
    allocation: dict[str, float] = {}
    asset_count = len(assets)

    for asset in assets:
        computed = _compute_asset_fields(asset)
        mv = computed["market_value"] or 0.0
        total_market_value += mv

        quantity = float(asset.quantity) if asset.quantity is not None else 0.0
        pp = float(asset.purchase_price) if asset.purchase_price is not None else 0.0
        total_cost += quantity * pp

        allocation[asset.asset_type] = allocation.get(asset.asset_type, 0.0) + mv

    total_pnl = total_market_value - total_cost
    total_pnl_pct = round((total_pnl / total_cost) * 100, 2) if total_cost > 0 else None

    # Convert allocation to percentages
    if total_market_value > 0:
        allocation = {
            k: round((v / total_market_value) * 100, 2)
            for k, v in allocation.items()
        }

    return {
        "total_market_value": total_market_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "allocation": allocation,
        "asset_count": asset_count,
    }
