"""portfolio_service — legacy API adapter over wealth/services/asset_service.

Bridges the V1 /portfolio router (PortfolioAsset schema with quantity,
purchase_price, current_price) to the Phase 3A Asset model so that the
old API keeps working while all data lives in the ``assets`` table.

Mapping convention (stored in asset.extra JSONB):
  extra["quantity"]  ↔  old quantity field
  extra["avg_price"] ↔  old purchase_price field
  (current_price is derived: current_value / quantity)
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.models.asset import Asset
from backend.wealth.services import asset_service
from backend.schemas.portfolio import PortfolioAssetCreate, PortfolioAssetUpdate


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_asset_fields(asset: Asset) -> dict:
    """Compute P&L and market value from Asset.current_value / initial_value."""
    mv = float(asset.current_value or 0)
    cost = float(asset.initial_value or 0)
    unrealized_pnl = mv - cost
    unrealized_pnl_pct = round((unrealized_pnl / cost) * 100, 2) if cost > 0 else None
    return {
        "market_value": mv,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
    }


def enrich_asset_response(asset: Asset) -> dict:
    """Adapt Asset to the legacy PortfolioAssetResponse shape.

    Reconstructs quantity / purchase_price / current_price from
    extra JSONB so callers that expect the old API shape keep working.
    """
    extra = asset.extra or {}
    quantity = extra.get("quantity")
    avg_price = extra.get("avg_price")

    # Derive current_price from current_value ÷ quantity when available
    if quantity and float(quantity) > 0:
        current_price = float(
            Decimal(str(asset.current_value or 0)) / Decimal(str(quantity))
        )
    else:
        current_price = float(asset.current_value or 0)

    # Strip internal fields from metadata so the response stays clean
    _internal = {"quantity", "avg_price"}
    metadata = {k: v for k, v in extra.items() if k not in _internal} or None

    data = {
        "id": asset.id,
        "user_id": asset.user_id,
        "asset_type": asset.asset_type,
        "name": asset.name,
        "quantity": float(quantity) if quantity is not None else None,
        "purchase_price": float(avg_price) if avg_price is not None else float(asset.initial_value or 0),
        "current_price": current_price,
        "metadata": metadata,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }
    data.update(_compute_asset_fields(asset))
    return data


def _initial_from(
    quantity: float | None,
    purchase_price: float | None,
) -> Decimal:
    """Compute initial_value from (optional) quantity × purchase_price."""
    if quantity is not None and purchase_price is not None:
        return Decimal(str(quantity)) * Decimal(str(purchase_price))
    if purchase_price is not None:
        return Decimal(str(purchase_price))
    return Decimal(0)


def _current_from(
    quantity: float | None,
    current_price: float | None,
    initial_value: Decimal,
) -> Decimal:
    """Compute current_value with a fallback chain to initial_value."""
    if quantity is not None and current_price is not None:
        return Decimal(str(quantity)) * Decimal(str(current_price))
    if current_price is not None:
        return Decimal(str(current_price))
    return initial_value


def _build_extra(
    quantity: float | None,
    purchase_price: float | None,
    metadata: dict | None,
) -> dict | None:
    """Build the extra JSONB dict from V1 fields."""
    extra: dict = {}
    if quantity is not None:
        extra["quantity"] = quantity
    if purchase_price is not None:
        extra["avg_price"] = purchase_price
    if metadata:
        extra.update(metadata)
    return extra or None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def create_asset(
    db: AsyncSession, user_id: uuid.UUID, data: PortfolioAssetCreate
) -> Asset:
    initial_value = _initial_from(data.quantity, data.purchase_price)
    current_value = _current_from(data.quantity, data.current_price, initial_value)
    extra = _build_extra(data.quantity, data.purchase_price, data.metadata)
    return await asset_service.create_asset(
        db,
        user_id,
        asset_type=data.asset_type,
        name=data.name,
        initial_value=initial_value,
        current_value=current_value,
        extra=extra,
    )


async def get_asset(
    db: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID
) -> Asset | None:
    return await asset_service.get_asset_by_id(db, user_id, asset_id)


async def list_assets(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Asset]:
    assets = await asset_service.get_user_assets(db, user_id, asset_type=asset_type)
    return assets[offset : offset + limit]


async def update_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    data: PortfolioAssetUpdate,
) -> Asset | None:
    asset = await asset_service.get_asset_by_id(db, user_id, asset_id)
    if asset is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # Simple field updates (direct ORM mutation — service owns the flush)
    if "name" in update_data:
        asset.name = update_data["name"]
    if "asset_type" in update_data:
        asset.asset_type = update_data["asset_type"]

    # Value updates: recompute initial_value / current_value and refresh extra
    has_value_change = any(
        k in update_data for k in ("quantity", "purchase_price", "current_price")
    )
    if has_value_change:
        existing = asset.extra or {}
        quantity = update_data.get("quantity", existing.get("quantity"))
        avg_price = update_data.get("purchase_price", existing.get("avg_price"))
        current_price = update_data.get("current_price")

        new_initial = _initial_from(quantity, avg_price)
        new_current = _current_from(quantity, current_price, new_initial)

        asset.initial_value = new_initial
        asset.current_value = new_current
        asset.last_valued_at = datetime.utcnow()

        # Rebuild extra: preserve non-internal keys, then update quantity/avg_price
        _internal = {"quantity", "avg_price"}
        new_extra = {k: v for k, v in existing.items() if k not in _internal}
        if quantity is not None:
            new_extra["quantity"] = quantity
        if avg_price is not None:
            new_extra["avg_price"] = avg_price
        if "metadata" in update_data and update_data["metadata"]:
            new_extra.update(update_data["metadata"])
        asset.extra = new_extra or None

    elif "metadata" in update_data:
        existing = asset.extra or {}
        _internal = {"quantity", "avg_price"}
        base = {k: v for k, v in existing.items() if k in _internal}
        if update_data["metadata"]:
            base.update(update_data["metadata"])
        asset.extra = base or None

    await db.flush()
    await db.refresh(asset)
    return asset


async def delete_asset(
    db: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID
) -> bool:
    try:
        await asset_service.soft_delete(db, user_id, asset_id)
        return True
    except ValueError:
        return False


async def get_portfolio_summary(
    db: AsyncSession, user_id: uuid.UUID
) -> dict:
    assets = await asset_service.get_user_assets(db, user_id)

    total_market_value = 0.0
    total_cost = 0.0
    allocation: dict[str, float] = {}
    asset_count = len(assets)

    for asset in assets:
        mv = float(asset.current_value or 0)
        cost = float(asset.initial_value or 0)
        total_market_value += mv
        total_cost += cost
        allocation[asset.asset_type] = allocation.get(asset.asset_type, 0.0) + mv

    total_pnl = total_market_value - total_cost
    total_pnl_pct = round((total_pnl / total_cost) * 100, 2) if total_cost > 0 else None

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
