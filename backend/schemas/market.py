import uuid
from datetime import date

from pydantic import BaseModel


class MarketSnapshotResponse(BaseModel):
    id: uuid.UUID
    snapshot_date: date
    asset_code: str
    asset_type: str
    asset_name: str | None
    price: float | None
    change_1d_pct: float | None
    change_1w_pct: float | None
    change_1m_pct: float | None
    extra_data: dict | None

    model_config = {"from_attributes": True}


class InvestmentAdviceRequest(BaseModel):
    user_id: uuid.UUID
