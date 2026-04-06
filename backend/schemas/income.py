import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


VALID_INCOME_TYPES = ["active", "passive"]

VALID_INCOME_SOURCES = [
    "salary", "dividend", "rental", "crypto_yield",
    "insurance", "gold", "fund_profit", "other",
]


class IncomeRecordCreate(BaseModel):
    income_type: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1, max_length=50)
    asset_id: uuid.UUID | None = None
    amount: float = Field(..., gt=0)
    period: date = Field(default_factory=lambda: date.today().replace(day=1))
    note: str | None = None


class IncomeRecordUpdate(BaseModel):
    income_type: str | None = Field(default=None, min_length=1)
    source: str | None = Field(default=None, min_length=1, max_length=50)
    asset_id: uuid.UUID | None = None
    amount: float | None = Field(default=None, gt=0)
    period: date | None = None
    note: str | None = None


class IncomeRecordResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    income_type: str
    source: str
    asset_id: uuid.UUID | None
    amount: float
    period: date
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IncomeSummary(BaseModel):
    period_start: date
    period_end: date
    total_active: float
    total_passive: float
    total: float
    passive_ratio: float | None
    by_source: dict[str, float]
