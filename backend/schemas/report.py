import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class ReportResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    month_key: str
    total_expense: float
    total_income: float | None
    savings_amount: float | None
    savings_rate: float | None
    breakdown_by_category: dict
    vs_previous_month: dict | None
    goal_progress: dict | None
    report_text: str | None
    generated_at: datetime

    model_config = {"from_attributes": True}


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
