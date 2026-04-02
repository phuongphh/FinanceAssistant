import uuid
from datetime import datetime

from pydantic import BaseModel


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
