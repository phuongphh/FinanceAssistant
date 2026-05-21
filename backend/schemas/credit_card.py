import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreditCardCreate(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=120)
    closing_date: int = Field(..., ge=1, le=31)
    debt_balance: float = Field(default=0, ge=0)


class CreditCardUpdate(BaseModel):
    bank_name: str | None = Field(default=None, min_length=2, max_length=120)
    closing_date: int | None = Field(default=None, ge=1, le=31)
    debt_balance: float | None = Field(default=None, ge=0)


class CreditCardResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    bank_name: str
    closing_date: int
    debt_balance: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
