import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class GoalCreate(BaseModel):
    goal_name: str = Field(..., min_length=1, max_length=500)
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(default=0, ge=0)
    deadline: date | None = None
    priority: str = Field(default="medium", pattern=r"^(high|medium|low)$")


class GoalUpdate(BaseModel):
    goal_name: str | None = Field(default=None, min_length=1, max_length=500)
    target_amount: float | None = Field(default=None, gt=0)
    deadline: date | None = None
    priority: str | None = Field(default=None, pattern=r"^(high|medium|low)$")
    is_active: bool | None = None


class GoalProgressUpdate(BaseModel):
    current_amount: float = Field(..., ge=0)


class GoalResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    goal_name: str
    target_amount: float
    current_amount: float
    deadline: date | None
    priority: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IncomeUpdate(BaseModel):
    monthly_income: float = Field(..., gt=0)
