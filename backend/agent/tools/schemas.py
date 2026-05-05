"""Pydantic schemas for tool inputs and outputs.

These schemas serve four jobs at once:

1. Generate JSON Schema for LLM function-calling (DeepSeek / Claude).
2. Validate LLM-produced arguments before execution.
3. Provide typed return values that formatters can rely on.
4. Document the agent surface for tests + future tools.

Design rules:

- Money fields use ``Decimal`` (CLAUDE.md §13). Filters take ``float``
  because LLM JSON tooling produces floats; we coerce safely on the
  comparison side.
- Enums constrain LLM outputs to known values — picking an unknown
  ``asset_type`` or ``sort`` order is impossible by construction.
- Every user-facing field has a ``Field(description=...)``: the LLM
  reads those descriptions to decide how to fill the params.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AssetType(str, Enum):
    """Asset classes recognised across the system. Mirrors
    ``backend.wealth.asset_types.AssetType`` so values round-trip."""

    STOCK = "stock"
    REAL_ESTATE = "real_estate"
    CRYPTO = "crypto"
    GOLD = "gold"
    CASH = "cash"
    OTHER = "other"


class SortOrder(str, Enum):
    """Sort orders the agent can request on asset lists.

    Naming convention: ``<field>_<asc|desc>``. ``gain`` is absolute
    VND gain, ``gain_pct`` is percentage. ``created_desc`` returns
    most-recently-added first."""

    VALUE_ASC = "value_asc"
    VALUE_DESC = "value_desc"
    GAIN_ASC = "gain_asc"
    GAIN_DESC = "gain_desc"
    GAIN_PCT_ASC = "gain_pct_asc"
    GAIN_PCT_DESC = "gain_pct_desc"
    NAME = "name"
    CREATED_DESC = "created_desc"


class TransactionCategory(str, Enum):
    """Spending categories recognised by the transaction system.

    Kept aligned with categories used by Phase 3.5 expense handlers
    (see ``backend/config/categories.py``)."""

    FOOD = "food"
    TRANSPORT = "transport"
    HOUSING = "housing"
    SHOPPING = "shopping"
    HEALTH = "health"
    EDUCATION = "education"
    ENTERTAINMENT = "entertainment"
    UTILITY = "utility"
    GIFT = "gift"
    SAVING = "saving"
    INVESTMENT = "investment"
    TRANSFER = "transfer"
    OTHER = "other"


class MetricName(str, Enum):
    """Aggregate metrics the agent can compute via ``ComputeMetricTool``."""

    SAVING_RATE = "saving_rate"
    NET_WORTH_GROWTH = "net_worth_growth"
    PORTFOLIO_TOTAL_GAIN = "portfolio_total_gain"
    PORTFOLIO_TOTAL_GAIN_PCT = "portfolio_total_gain_pct"
    AVERAGE_MONTHLY_EXPENSE = "average_monthly_expense"
    EXPENSE_TO_INCOME_RATIO = "expense_to_income_ratio"
    DIVERSIFICATION_SCORE = "diversification_score"


class ComparePeriod(str, Enum):
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_YEAR = "this_year"
    LAST_YEAR = "last_year"


class CompareMetric(str, Enum):
    EXPENSES = "expenses"
    INCOME = "income"
    NET_WORTH = "net_worth"
    SAVINGS = "savings"


# ---------------------------------------------------------------------------
# Filter primitives
# ---------------------------------------------------------------------------


class _StrictBase(BaseModel):
    """Reject unknown fields — the LLM occasionally hallucinates extra
    keys, and silent-accepting them masks prompt regressions."""

    model_config = ConfigDict(extra="forbid")


class NumericFilter(_StrictBase):
    """Range filter for numeric fields.

    Mix-and-match supported — ``{gt: 0, lt: 1000}`` means ``0 < x < 1000``.
    All bounds optional; an empty filter matches everything (in which
    case the caller should just omit the filter)."""

    gt: Optional[float] = Field(None, description="Strictly greater than")
    gte: Optional[float] = Field(None, description="Greater than or equal")
    lt: Optional[float] = Field(None, description="Strictly less than")
    lte: Optional[float] = Field(None, description="Less than or equal")
    eq: Optional[float] = Field(None, description="Equals (within 0.001)")


class AssetFilter(_StrictBase):
    """Filter conditions for ``GetAssetsTool``.

    For "đang lãi" use ``gain_pct={gt: 0}``. For "đang lỗ" use
    ``gain_pct={lt: 0}``. For "trên 1 tỷ" use ``value={gt: 1_000_000_000}``.
    """

    asset_type: Optional[AssetType] = Field(
        None, description="Restrict to a single asset class."
    )
    ticker: Optional[list[str]] = Field(
        None,
        description=(
            "Match assets whose stock/crypto ticker is in this list. "
            "Case-insensitive. e.g. ['VNM', 'HPG']."
        ),
    )
    value: Optional[NumericFilter] = Field(
        None, description="Filter on the asset's current_value (VND)."
    )
    gain_pct: Optional[NumericFilter] = Field(
        None,
        description=(
            "Filter on percentage gain vs initial_value. "
            "Use {gt: 0} for winners, {lt: 0} for losers."
        ),
    )


class TransactionFilter(_StrictBase):
    category: Optional[TransactionCategory] = None
    date_from: Optional[date] = Field(None, description="Inclusive lower date bound.")
    date_to: Optional[date] = Field(None, description="Inclusive upper date bound.")
    amount: Optional[NumericFilter] = None


# ---------------------------------------------------------------------------
# Tool input models
# ---------------------------------------------------------------------------


class GetAssetsInput(_StrictBase):
    """Inputs for ``get_assets``.

    Empty input lists every active asset, sorted by created_desc by
    default. Combine ``filter``, ``sort``, ``limit`` to answer "top N
    cổ phiếu lãi nhất", "tài sản trên 1 tỷ", etc."""

    filter: Optional[AssetFilter] = Field(
        None,
        description=(
            "Filter assets by type, ticker, value, or gain%. "
            "Use this for 'cổ phiếu đang lãi' (gain_pct.gt=0), "
            "'tài sản >1tỷ' (value.gt=1_000_000_000)."
        ),
    )
    sort: Optional[SortOrder] = Field(
        None,
        description=(
            "Sort order. Use 'gain_pct_desc' for top performers, "
            "'value_desc' for largest holdings."
        ),
    )
    limit: Optional[int] = Field(
        None,
        ge=1,
        le=100,
        description="Cap result count. Use 3 for 'top 3' queries.",
    )


class GetTransactionsInput(_StrictBase):
    filter: Optional[TransactionFilter] = None
    sort: Optional[Literal["date_desc", "date_asc", "amount_desc", "amount_asc"]] = (
        Field(None, description="Default ordering is date_desc.")
    )
    limit: Optional[int] = Field(None, ge=1, le=200)


class ComputeMetricInput(_StrictBase):
    metric_name: MetricName = Field(
        ..., description="Which financial metric to compute."
    )
    period_months: Optional[int] = Field(
        None,
        ge=1,
        le=60,
        description=(
            "Look-back window in months. Defaults: saving_rate / "
            "expense ratios use 1 month; growth metrics use 12; "
            "portfolio gain ignores this field."
        ),
    )


class ComparePeriodsInput(_StrictBase):
    metric: CompareMetric = Field(..., description="What to compare across periods.")
    period_a: ComparePeriod
    period_b: ComparePeriod


class GetMarketDataInput(_StrictBase):
    ticker: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Ticker symbol (e.g. 'VNM', 'BTC', 'VNINDEX'). Case-insensitive.",
    )
    period: Optional[Literal["1d", "7d", "30d", "90d", "365d"]] = Field(
        "1d", description="Look-back window for change %."
    )


# ---------------------------------------------------------------------------
# Tool output models
# ---------------------------------------------------------------------------


class AssetItem(BaseModel):
    """One asset row in a tool result."""

    name: str
    asset_type: str
    ticker: Optional[str] = None
    quantity: Optional[float] = None
    current_value: Decimal
    cost_basis: Optional[Decimal] = None
    gain: Optional[Decimal] = None
    gain_pct: Optional[float] = None


class GetAssetsOutput(BaseModel):
    assets: list[AssetItem]
    total_value: Decimal
    count: int


class TransactionItem(BaseModel):
    date: date
    merchant: Optional[str] = None
    category: str
    amount: Decimal
    note: Optional[str] = None


class GetTransactionsOutput(BaseModel):
    transactions: list[TransactionItem]
    total_amount: Decimal
    count: int


class MetricResult(BaseModel):
    metric_name: str
    value: float
    unit: Literal["vnd", "percent", "score"]
    period: str
    context: Optional[str] = Field(
        None, description="Human-readable explanation, e.g. 'last 30 days'."
    )


class ComparisonResult(BaseModel):
    metric: str
    period_a_value: Decimal
    period_b_value: Decimal
    diff_absolute: Decimal
    diff_percent: float
    period_a_label: str
    period_b_label: str


class MarketDataPoint(BaseModel):
    ticker: str
    asset_name: Optional[str] = None
    current_price: Decimal
    change_pct: Optional[float] = None
    period: str
    user_owns: bool = False
    user_quantity: Optional[float] = None
    user_holding_value: Optional[Decimal] = None
    note: Optional[str] = None
