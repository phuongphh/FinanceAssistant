import uuid
from datetime import datetime

from pydantic import BaseModel, Field


VALID_ASSET_TYPES = [
    "real_estate", "stocks", "mutual_fund",
    "crypto", "life_insurance", "gold",
]


class PortfolioAssetCreate(BaseModel):
    asset_type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=200)
    quantity: float | None = None
    purchase_price: float | None = Field(default=None, ge=0)
    current_price: float | None = Field(default=None, ge=0)
    metadata: dict | None = None


class PortfolioAssetUpdate(BaseModel):
    asset_type: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: float | None = None
    purchase_price: float | None = Field(default=None, ge=0)
    current_price: float | None = Field(default=None, ge=0)
    metadata: dict | None = None


class PortfolioAssetResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    asset_type: str
    name: str
    quantity: float | None
    purchase_price: float | None
    current_price: float | None
    metadata: dict | None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    market_value: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PortfolioSummary(BaseModel):
    total_market_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float | None
    allocation: dict[str, float]
    asset_count: int
