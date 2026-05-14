from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Invalid email address")
    return value


class AdminUserOut(BaseModel):
    id: int
    email: str
    full_name: str | None = None
    role: str
    tenant_id: int | None = None
    is_active: bool
    force_password_change: bool
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    force_password_change: bool
    admin: AdminUserOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
            raise ValueError("Password must contain at least one letter and one number")
        return value


class AuditLogEntryOut(BaseModel):
    id: int
    admin_user_id: int | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    payload: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[AuditLogEntryOut]


class OverviewMetrics(BaseModel):
    total_users: int
    total_users_delta_pct: float
    new_users_period: int
    new_users_delta_pct: float = 0.0
    dau: int
    dau_delta_pct: float
    wau: int
    mau: int
    stickiness_pct: float
    activation_rate_pct: float
    total_llm_cost_usd: float
    cost_delta_pct: float
    avg_cost_per_active_user: float
    asset_coverage_pct: float
    briefing_open_rate_pct: float
    error_rate_pct: float


class OverviewStatsResponse(BaseModel):
    period: str
    generated_at: datetime
    metrics: OverviewMetrics


class UserGrowthPoint(BaseModel):
    date: date
    cumulative: int
    new_users: int


class UserGrowthResponse(BaseModel):
    data: list[UserGrowthPoint]


class DauPoint(BaseModel):
    date: date
    dau: int


class DauChartResponse(BaseModel):
    data: list[DauPoint]


class FeatureClickPoint(BaseModel):
    feature_key: str
    feature_name: str
    clicks: int


class FeatureClicksResponse(BaseModel):
    data: list[FeatureClickPoint]


class IntentBreakdownPoint(BaseModel):
    resolved_by: str
    label: str
    count: int
    pct: float


class IntentBreakdownResponse(BaseModel):
    data: list[IntentBreakdownPoint]


class UserTierPoint(BaseModel):
    tier: str
    label: str
    count: int


class UserTiersResponse(BaseModel):
    data: list[UserTierPoint]


class CohortRetentionRow(BaseModel):
    cohort_week: date
    cohort_size: int
    retention: dict[str, int | None]


class CohortRetentionResponse(BaseModel):
    cohorts: list[CohortRetentionRow]
