import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

VALID_CATEGORIES = [
    "food_drink",
    "transport",
    "shopping",
    "health",
    "entertainment",
    "utilities",
    "investment",
    "savings",
    "other",
    "needs_review",
]

VALID_SOURCES = ["gmail", "ocr", "manual", "bank_sync"]
VALID_TRANSACTION_TYPES = ["expense", "money_in"]
VALID_SOURCE_TYPES = ["cash", "bank_account", "e_wallet", "credit_card"]
VALID_E_WALLET_PROVIDERS = ["momo", "vnpay", "zalopay", "viettelpay"]


class ExpenseCreate(BaseModel):
    amount: float = Field(..., gt=0)
    transaction_type: str = Field(default="expense")
    currency: str = Field(default="VND", max_length=10)
    merchant: str | None = None
    category: str = Field(default="needs_review")
    source: str = Field(default="manual")
    source_asset_id: uuid.UUID | None = None
    source_credit_card_id: uuid.UUID | None = None
    source_type: str | None = None
    e_wallet_provider: str | None = None
    expense_date: date = Field(default_factory=date.today)
    note: str | None = None
    raw_data: dict | None = None
    needs_review: bool = False
    gmail_message_id: str | None = None

    @field_validator("transaction_type")
    @classmethod
    def validate_transaction_type(cls, value: str) -> str:
        if value not in VALID_TRANSACTION_TYPES:
            raise ValueError("transaction_type must be expense or money_in")
        return value

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_SOURCE_TYPES:
            raise ValueError("source_type is not supported")
        return value

    @field_validator("e_wallet_provider")
    @classmethod
    def validate_wallet_provider(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_E_WALLET_PROVIDERS:
            raise ValueError("e_wallet_provider is not supported")
        return value


class ExpenseUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    transaction_type: str | None = None
    currency: str | None = None
    merchant: str | None = None
    category: str | None = None
    source_asset_id: uuid.UUID | None = None
    source_credit_card_id: uuid.UUID | None = None
    source_type: str | None = None
    e_wallet_provider: str | None = None
    expense_date: date | None = None
    note: str | None = None
    raw_data: dict | None = None
    needs_review: bool | None = None

    @field_validator("transaction_type")
    @classmethod
    def validate_update_transaction_type(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_TRANSACTION_TYPES:
            raise ValueError("transaction_type must be expense or money_in")
        return value

    @field_validator("source_type")
    @classmethod
    def validate_update_source_type(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_SOURCE_TYPES:
            raise ValueError("source_type is not supported")
        return value

    @field_validator("e_wallet_provider")
    @classmethod
    def validate_update_wallet_provider(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_E_WALLET_PROVIDERS:
            raise ValueError("e_wallet_provider is not supported")
        return value


class ExpenseResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: float
    transaction_type: str
    currency: str
    merchant: str | None
    category: str
    source: str
    source_asset_id: uuid.UUID | None
    source_credit_card_id: uuid.UUID | None
    source_type: str | None
    e_wallet_provider: str | None
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
