import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


VALID_CATEGORIES = [
    "food_drink", "transport", "shopping", "health",
    "entertainment", "utilities", "investment",
    "savings", "other", "needs_review",
]

VALID_SOURCES = ["gmail", "ocr", "manual", "bank_sync"]


class ExpenseCreate(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = Field(default="VND", max_length=10)
    merchant: str | None = None
    category: str = Field(default="needs_review")
    source: str = Field(default="manual")
    expense_date: date = Field(default_factory=date.today)
    note: str | None = None
    raw_data: dict | None = None
    needs_review: bool = False
    gmail_message_id: str | None = None


class ExpenseUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    currency: str | None = None
    merchant: str | None = None
    category: str | None = None
    note: str | None = None
    needs_review: bool | None = None


class ExpenseResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: float
    currency: str
    merchant: str | None
    category: str
    source: str
    expense_date: date
    month_key: str
    note: str | None
    needs_review: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExpenseSummary(BaseModel):
    month_key: str
    total: float
    by_category: dict[str, float]
    count: int
