# Phase 3.7 — Agent Architecture (Chi Tiết Triển Khai)

> **Đây là phase architectural inflection point — biến Bé Tiền từ "intent classifier" thành "AI agent" có thể trả lời 95% queries về tài chính cá nhân.**

> **Thời gian ước tính:** 3 tuần  
> **Mục tiêu cuối Phase:** Bé Tiền trả lời được 5 loại queries Phase 3.5 không handle được:
> 1. Filtered queries ("Mã nào đang lãi?")
> 2. Sorted/Top-N queries ("Top 3 mã lãi nhiều nhất")
> 3. Computed/Aggregate queries ("Tổng lãi portfolio")
> 4. Comparison queries ("VNM vs HPG")
> 5. Multi-step reasoning ("Có nên bán FLC không?")
>
> **Điều kiện "Done":** Cost average <$0.001/query, latency p95 <5s for Tier 2, <10s for Tier 3, accuracy ≥90% on test suite.

> **Prerequisites:** Phase 3.5 (intent layer) + Phase 3.6 (menu) đã ship. Phase 3.7 đứng **trước** Phase 3B (theo decision của user).

---

## 🎯 Triết Lý Thiết Kế Phase 3.7

Đây là 6 nguyên lý quan trọng nhất:

### 1. "Extend, Don't Replace"
Phase 3.5 đã build intent layer + 22 stories. Phase 3.7 **mở rộng** không **thay thế**. Existing handlers trở thành tools mà agent có thể call. Zero throwaway work.

### 2. "Right Model for Right Job"
Two fundamentally different problems need two different solutions:
- **DB queries** (filter/sort/aggregate) → cheap LLM (DeepSeek) → SQL-like tools → DB execution
- **Reasoning queries** (advisory, planning) → premium LLM (Claude Sonnet) → multi-step thinking

→ Orchestrator routes correctly.

### 3. "LLM Selects Tools, Code Executes Tools"
LLM **không generate SQL**. LLM **chỉ chọn predefined tool + extract typed params**. Tool execution là deterministic Python code. Pattern này:
- ✅ Safe (no injection)
- ✅ Auditable (every call logged)
- ✅ Testable (tools have unit tests)
- ✅ Cheaper (LLM does less work)

### 4. "Heuristic First, LLM When Needed"
Routing decisions use heuristic keywords first (free, instant). LLM classifier only when heuristics ambiguous. Avoid spending LLM tokens on routing.

### 5. "Streaming for Long Operations"
Tier 3 reasoning takes 5-15s. Without streaming, user perceives it as "broken". Streaming via Telegram chunked messages + typing indicator keeps engagement.

### 6. "Cap Everything"
LLM agent có thể infinite loop or runaway cost. Hard caps on:
- Max tool calls per query (5)
- Max tokens per query (10000)
- Timeout per query (30s)
- Max queries per user per hour (rate limit)

---

## 📅 Phân Bổ Thời Gian (3 tuần)

| Tuần | Nội dung | Deliverable |
|------|----------|-------------|
| **Tuần 1** | Tool Foundation + DB-Agent (Tier 2) | Tier 2 working — handles loại #1-4 |
| **Tuần 2** | Premium Reasoning (Tier 3) + Orchestrator | Tier 3 + routing — handles loại #5 |
| **Tuần 3** | Streaming + Polish + Testing | Production-ready, user tested |

---

## 🗂️ Cấu Trúc Thư Mục Mở Rộng

```
finance_assistant/
├── app/
│   ├── agent/                          # ⭐ NEW - Core của Phase 3.7
│   │   ├── __init__.py
│   │   ├── orchestrator.py             # Routing logic
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # Tool interface + registry
│   │   │   ├── schemas.py              # Pydantic models for tool inputs/outputs
│   │   │   ├── get_assets.py
│   │   │   ├── get_transactions.py
│   │   │   ├── compute_metric.py
│   │   │   ├── compare_periods.py
│   │   │   └── get_market_data.py
│   │   ├── tier2/
│   │   │   ├── __init__.py
│   │   │   ├── db_agent.py             # DeepSeek + function calling
│   │   │   └── prompts.py
│   │   ├── tier3/
│   │   │   ├── __init__.py
│   │   │   ├── reasoning_agent.py      # Claude Sonnet + multi-step
│   │   │   └── prompts.py
│   │   ├── streaming/
│   │   │   ├── __init__.py
│   │   │   └── telegram_streamer.py    # Chunked message delivery
│   │   ├── caching.py                  # Tier 2 + Tier 3 caches
│   │   └── audit.py                    # Logging tool calls
│   │
│   └── ...
│
├── content/
│   └── router_heuristics.yaml          # ⭐ NEW - Routing keywords
│
└── tests/
    └── test_agent/
        ├── test_orchestrator.py
        ├── test_tools/
        │   ├── test_get_assets.py
        │   └── ...
        ├── test_db_agent.py
        ├── test_reasoning_agent.py
        └── fixtures/
            └── tier_test_queries.yaml
```

---

# 🔧 TUẦN 1: Tool Foundation + DB-Agent (Tier 2)

## 1.1 — Tool Schema Design (CRITICAL FOUNDATION)

Đây là phần quan trọng nhất của toàn phase. Schema design tốt = LLM dễ chọn đúng tool. Schema design tệ = bugs, miscalls, frustration.

### File: `app/agent/tools/schemas.py`

```python
"""
Pydantic schemas for tool inputs and outputs.
Used by both LLM (as JSON schema) and Python (for validation).
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


# === Enums ===

class AssetType(str, Enum):
    STOCK = "stock"
    REAL_ESTATE = "real_estate"
    CRYPTO = "crypto"
    GOLD = "gold"
    CASH = "cash"


class SortOrder(str, Enum):
    VALUE_ASC = "value_asc"
    VALUE_DESC = "value_desc"
    GAIN_ASC = "gain_asc"
    GAIN_DESC = "gain_desc"
    GAIN_PCT_ASC = "gain_pct_asc"
    GAIN_PCT_DESC = "gain_pct_desc"
    NAME = "name"
    CREATED_DESC = "created_desc"


class TransactionCategory(str, Enum):
    FOOD = "food"
    TRANSPORT = "transport"
    HOUSING = "housing"
    SHOPPING = "shopping"
    HEALTH = "health"
    EDUCATION = "education"
    ENTERTAINMENT = "entertainment"
    UTILITY = "utility"
    GIFT = "gift"
    INVESTMENT = "investment"


class MetricName(str, Enum):
    SAVING_RATE = "saving_rate"
    NET_WORTH_GROWTH = "net_worth_growth"
    PORTFOLIO_TOTAL_GAIN = "portfolio_total_gain"
    AVERAGE_MONTHLY_EXPENSE = "average_monthly_expense"
    EXPENSE_TO_INCOME_RATIO = "expense_to_income_ratio"
    DIVERSIFICATION_SCORE = "diversification_score"


# === Filter Models ===

class NumericFilter(BaseModel):
    """Filter for numeric fields. Supports range or comparison."""
    gt: Optional[float] = None  # greater than
    gte: Optional[float] = None  # greater than or equal
    lt: Optional[float] = None  # less than
    lte: Optional[float] = None  # less than or equal
    eq: Optional[float] = None  # equals


class AssetFilter(BaseModel):
    asset_type: Optional[AssetType] = None
    ticker: Optional[list[str]] = None  # e.g., ["VNM", "HPG"]
    value: Optional[NumericFilter] = None
    gain_pct: Optional[NumericFilter] = None  # e.g., {gt: 0} for gainers
    
    
class TransactionFilter(BaseModel):
    category: Optional[TransactionCategory] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    amount: Optional[NumericFilter] = None
    

# === Tool Input Models ===

class GetAssetsInput(BaseModel):
    """Get user's assets with optional filtering, sorting, limit."""
    filter: Optional[AssetFilter] = Field(
        None,
        description="Filter assets by type, value, gain. Use this for queries like 'cổ phiếu đang lãi' (gain_pct > 0)."
    )
    sort: Optional[SortOrder] = Field(
        None,
        description="Sort order. Use 'gain_pct_desc' for top performers."
    )
    limit: Optional[int] = Field(
        None,
        ge=1,
        le=100,
        description="Limit number of results. Use 3 for 'top 3' queries.",
    )


class GetTransactionsInput(BaseModel):
    """Get user's transactions with filtering."""
    filter: Optional[TransactionFilter] = None
    sort: Optional[Literal["date_desc", "amount_desc", "amount_asc"]] = None
    limit: Optional[int] = Field(None, ge=1, le=200)


class ComputeMetricInput(BaseModel):
    """Compute a financial metric for the user."""
    metric_name: MetricName
    period_months: Optional[int] = Field(
        None,
        ge=1,
        le=60,
        description="Period in months. Default: current month for monthly metrics."
    )


class ComparePeriodsInput(BaseModel):
    """Compare a metric across two time periods."""
    metric: Literal["expenses", "income", "net_worth", "savings"]
    period_a: Literal["this_month", "last_month", "this_year", "last_year"]
    period_b: Literal["this_month", "last_month", "this_year", "last_year"]


class GetMarketDataInput(BaseModel):
    """Get market data for a ticker."""
    ticker: str = Field(..., description="Ticker symbol (e.g., 'VNM', 'BTC', 'VNINDEX')")
    period: Optional[Literal["1d", "7d", "30d", "90d", "365d"]] = "1d"


# === Tool Output Models ===

class AssetItem(BaseModel):
    name: str
    asset_type: str
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
    merchant: Optional[str]
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
    unit: str  # "vnd", "percent", "score"
    period: str
    context: Optional[str] = None  # human-readable explanation


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
    current_price: Decimal
    change_pct: float
    period: str
    user_owns: bool = False
    user_quantity: Optional[float] = None
    user_holding_value: Optional[Decimal] = None
```

**Why Pydantic:**
- LLM gets clear JSON schema (auto-generated)
- Type safety in Python
- Validation prevents bad LLM outputs
- Same models used in tests

---

## 1.2 — Tool Implementations

### File: `app/agent/tools/base.py`

```python
"""
Base tool interface and registry.
"""

from abc import ABC, abstractmethod
from typing import Any, Type
from pydantic import BaseModel


class Tool(ABC):
    """Base class for all agent tools."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool identifier used by LLM."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Description shown to LLM for tool selection."""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> Type[BaseModel]:
        pass
    
    @property
    @abstractmethod
    def output_schema(self) -> Type[BaseModel]:
        pass
    
    @abstractmethod
    async def execute(self, input_data: BaseModel, user) -> BaseModel:
        """Execute the tool. Must be deterministic."""
        pass
    
    def to_openai_function(self) -> dict:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_json_schema(),
            }
        }


class ToolRegistry:
    """Central registry of available tools."""
    
    def __init__(self):
        self._tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool):
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)
    
    def list_all(self) -> list[Tool]:
        return list(self._tools.values())
    
    def to_openai_functions(self) -> list[dict]:
        return [t.to_openai_function() for t in self._tools.values()]
```

### File: `app/agent/tools/get_assets.py`

```python
"""
GetAssets tool - the most critical tool for Phase 3.7.
Handles all the queries Phase 3.5 couldn't.
"""

from app.agent.tools.base import Tool
from app.agent.tools.schemas import (
    GetAssetsInput, GetAssetsOutput, AssetItem, NumericFilter
)
from app.wealth.services.asset_service import AssetService


class GetAssetsTool(Tool):
    @property
    def name(self) -> str:
        return "get_assets"
    
    @property
    def description(self) -> str:
        return (
            "Retrieve user's assets with optional filtering, sorting, and limiting. "
            "Use this for ANY query about the user's holdings (assets, stocks, real estate, crypto, gold, cash). "
            "Examples of when to use:\n"
            "- 'tài sản của tôi' → no filter, no sort\n"
            "- 'mã chứng khoán nào của tôi đang lãi' → filter: {asset_type: stock, gain_pct: {gt: 0}}\n"
            "- 'top 3 mã lãi nhiều nhất' → filter: {asset_type: stock}, sort: gain_pct_desc, limit: 3\n"
            "- 'tài sản trên 1 tỷ' → filter: {value: {gt: 1000000000}}\n"
            "- 'mã đang lỗ' → filter: {asset_type: stock, gain_pct: {lt: 0}}, sort: gain_pct_asc"
        )
    
    @property
    def input_schema(self):
        return GetAssetsInput
    
    @property
    def output_schema(self):
        return GetAssetsOutput
    
    async def execute(self, input_data: GetAssetsInput, user) -> GetAssetsOutput:
        # Step 1: Get all user's assets via existing service
        all_assets = await AssetService().get_user_assets(user.id)
        
        # Step 2: Apply filters
        filtered = self._apply_filter(all_assets, input_data.filter)
        
        # Step 3: Compute gain/gain_pct (needed for sorting)
        items = [self._to_asset_item(a) for a in filtered]
        
        # Step 4: Apply sorting
        if input_data.sort:
            items = self._apply_sort(items, input_data.sort)
        
        # Step 5: Apply limit
        if input_data.limit:
            items = items[:input_data.limit]
        
        # Step 6: Aggregate
        total_value = sum((item.current_value for item in items), start=Decimal(0))
        
        return GetAssetsOutput(
            assets=items,
            total_value=total_value,
            count=len(items),
        )
    
    def _apply_filter(self, assets, filter):
        if not filter:
            return assets
        
        result = assets
        
        if filter.asset_type:
            result = [a for a in result if a.asset_type == filter.asset_type.value]
        
        if filter.ticker:
            result = [a for a in result if (a.metadata.get("ticker") or "").upper() in [t.upper() for t in filter.ticker]]
        
        if filter.value:
            result = [a for a in result if self._matches_numeric(float(a.current_value), filter.value)]
        
        if filter.gain_pct:
            # Must compute gain_pct first
            result = [
                a for a in result
                if a.cost_basis
                and self._matches_numeric(self._compute_gain_pct(a), filter.gain_pct)
            ]
        
        return result
    
    def _matches_numeric(self, value: float, f: NumericFilter) -> bool:
        if f.gt is not None and not (value > f.gt): return False
        if f.gte is not None and not (value >= f.gte): return False
        if f.lt is not None and not (value < f.lt): return False
        if f.lte is not None and not (value <= f.lte): return False
        if f.eq is not None and not (abs(value - f.eq) < 0.001): return False
        return True
    
    def _compute_gain_pct(self, asset) -> float:
        if not asset.cost_basis or asset.cost_basis == 0:
            return 0.0
        return float((asset.current_value - asset.cost_basis) / asset.cost_basis * 100)
    
    def _to_asset_item(self, asset) -> AssetItem:
        gain = None
        gain_pct = None
        if asset.cost_basis:
            gain = asset.current_value - asset.cost_basis
            gain_pct = self._compute_gain_pct(asset)
        
        return AssetItem(
            name=asset.name,
            asset_type=asset.asset_type,
            quantity=asset.metadata.get("quantity"),
            current_value=asset.current_value,
            cost_basis=asset.cost_basis,
            gain=gain,
            gain_pct=gain_pct,
        )
    
    def _apply_sort(self, items: list[AssetItem], sort_order) -> list[AssetItem]:
        sort_map = {
            "value_asc": lambda x: x.current_value,
            "value_desc": lambda x: -x.current_value,
            "gain_asc": lambda x: x.gain or Decimal(0),
            "gain_desc": lambda x: -(x.gain or Decimal(0)),
            "gain_pct_asc": lambda x: x.gain_pct if x.gain_pct is not None else 0,
            "gain_pct_desc": lambda x: -(x.gain_pct if x.gain_pct is not None else 0),
            "name": lambda x: x.name,
        }
        key_fn = sort_map.get(sort_order.value, lambda x: 0)
        return sorted(items, key=key_fn)
```

**Critical implementation note:** This tool wraps `AssetService` (Phase 3A) without modifying it. **Existing logic intact**, new filter/sort/limit added on top.

### Other Tools (sketches)

`get_transactions.py`, `compute_metric.py`, `compare_periods.py`, `get_market_data.py` follow same pattern. Each:
- Wraps existing Phase 3A/3.5 service
- Adds filter/sort/aggregate layer
- Returns Pydantic-validated output
- Has comprehensive description for LLM

---

## 1.3 — Tier 2: DB-Agent (DeepSeek + Function Calling)

### File: `app/agent/tier2/db_agent.py`

```python
"""
Tier 2 agent: DB-backed queries via DeepSeek function calling.
Handles loại #1-4 (filter, sort, aggregate, comparison).
"""

import json
from openai import AsyncOpenAI
from app.config import settings
from app.agent.tools.base import ToolRegistry


DB_AGENT_SYSTEM_PROMPT = """Bạn là trợ lý tài chính cho người Việt. 

Nhiệm vụ: Translate Vietnamese finance queries to tool calls.

QUY TẮC:
1. Chọn ĐÚNG MỘT tool để answer query
2. Extract parameters CHÍNH XÁC từ Vietnamese text
3. Cho queries về "đang lãi" → filter gain_pct > 0
4. Cho queries về "đang lỗ" → filter gain_pct < 0
5. Cho queries về "top N" → set limit=N với sort phù hợp
6. Cho queries về aggregate (tổng, trung bình) → use compute_metric tool

VÍ DỤ:
"Mã nào đang lãi?" → get_assets(filter={asset_type: stock, gain_pct: {gt: 0}}, sort: gain_pct_desc)
"Top 3 mã lãi nhất" → get_assets(filter={asset_type: stock}, sort: gain_pct_desc, limit: 3)
"Chi cho ăn uống tuần này" → get_transactions(filter={category: food, date_from: ..., date_to: ...})
"Tỷ lệ tiết kiệm tháng này" → compute_metric(metric_name: saving_rate, period_months: 1)

Nếu query KHÔNG match tool nào → return text response giải thích không hiểu.
"""


class DBAgent:
    def __init__(self, registry: ToolRegistry):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
        )
        self.registry = registry
        self.tools_schema = registry.to_openai_functions()
    
    async def answer(self, query: str, user) -> dict:
        """
        Answer a query using tool calls.
        Returns: {"success": bool, "tool_called": str, "result": Any, "error": str}
        """
        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": DB_AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                tools=self.tools_schema,
                tool_choice="auto",
                max_tokens=500,
                temperature=0.0,
            )
            
            message = response.choices[0].message
            
            # Check if LLM called a tool
            if not message.tool_calls:
                return {
                    "success": False,
                    "tool_called": None,
                    "result": None,
                    "error": "no_tool_selected",
                    "fallback_text": message.content,
                }
            
            # Execute the tool
            tool_call = message.tool_calls[0]  # Take first only (Tier 2 = single-step)
            tool_name = tool_call.function.name
            tool_args_raw = tool_call.function.arguments
            
            tool = self.registry.get(tool_name)
            if not tool:
                return {
                    "success": False,
                    "tool_called": tool_name,
                    "error": f"unknown_tool: {tool_name}",
                }
            
            # Validate args via Pydantic
            try:
                tool_args_dict = json.loads(tool_args_raw)
                validated_input = tool.input_schema(**tool_args_dict)
            except Exception as e:
                return {
                    "success": False,
                    "tool_called": tool_name,
                    "error": f"invalid_args: {str(e)}",
                }
            
            # Execute
            result = await tool.execute(validated_input, user)
            
            return {
                "success": True,
                "tool_called": tool_name,
                "tool_args": validated_input.model_dump(),
                "result": result.model_dump(),
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"agent_error: {str(e)}",
            }
```

### Response Formatting

After tool execution, format result for user. Reuse Phase 3.5 formatters where possible:

```python
async def format_db_agent_response(result: dict, user, query: str) -> str:
    """Convert tool result to user-facing response."""
    
    tool_name = result["tool_called"]
    
    if tool_name == "get_assets":
        return format_assets_response(result["result"], user, query)
    elif tool_name == "get_transactions":
        return format_transactions_response(result["result"], user, query)
    elif tool_name == "compute_metric":
        return format_metric_response(result["result"], user)
    elif tool_name == "compare_periods":
        return format_comparison_response(result["result"], user)
    elif tool_name == "get_market_data":
        return format_market_response(result["result"], user)
```

Each formatter is wealth-level adaptive (reuse Phase 3.5 logic).

---

## ✅ Checklist Cuối Tuần 1

- [ ] All 5 tool schemas defined (Pydantic)
- [ ] All 5 tools implemented + unit tested
- [ ] ToolRegistry working with `to_openai_functions()`
- [ ] DBAgent calling DeepSeek with function calling
- [ ] DBAgent successfully translates 20+ Vietnamese queries to correct tool + args
- [ ] Output formatters cho 5 tools, wealth-level adaptive
- [ ] Critical test: "Mã chứng khoán nào của tôi đang lãi?" → returns ONLY winners
- [ ] Performance: avg DB-Agent response <2s

---

# 🧠 TUẦN 2: Premium Reasoning (Tier 3) + Orchestrator

## 2.1 — Tier 3: Reasoning Agent (Claude Sonnet)

### File: `app/agent/tier3/reasoning_agent.py`

```python
"""
Tier 3 agent: Multi-step reasoning via Claude Sonnet.
Handles loại #5 (advisory, what-if, planning).
"""

from anthropic import AsyncAnthropic
from app.config import settings
from app.agent.tools.base import ToolRegistry


REASONING_AGENT_SYSTEM_PROMPT = """Bạn là Bé Tiền — Personal CFO cá nhân cho người Việt.

VAI TRÒ:
Bạn giúp user thông qua reasoning multi-step về tài chính cá nhân.
Bạn có thể call tools nhiều lần để thu thập data, sau đó tổng hợp đưa ra advice.

TOOLS AVAILABLE:
{tool_descriptions}

QUY TẮC HARD:
1. KHÔNG khuyên mua/bán cổ phiếu cụ thể (lý do pháp lý)
2. KHÔNG hứa hẹn lợi nhuận cụ thể
3. LUÔN kết thúc với disclaimer: "Đây là gợi ý dựa trên data cá nhân, không phải lời khuyên đầu tư chuyên nghiệp"
4. Đưa ra 2-3 options cho user chọn, không 1 prescription
5. Nếu thiếu data, hỏi user thay vì đoán

QUY TẮC TONE:
- Xưng "mình", gọi user là "bạn" hoặc "{name}"
- Adapt theo wealth level (Starter: simple language, HNW: professional)
- Warm nhưng không nịnh nọt

CONTEXT USER:
- Tên: {name}
- Wealth level: {wealth_level}
- Net worth hiện tại: {net_worth}

FLOW:
1. Đọc query
2. Suy nghĩ data nào cần (call tools)
3. Tổng hợp + reason
4. Compose final answer

Tối đa 5 tool calls. Sau đó MUST compose final answer."""


class ReasoningAgent:
    def __init__(self, registry: ToolRegistry):
        self.client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.registry = registry
        self.max_tool_calls = 5
        self.max_tokens_total = 10000
    
    async def answer_streaming(self, query: str, user, on_chunk):
        """
        Answer with multi-step reasoning + streaming response.
        on_chunk: callback function called with each text chunk.
        """
        # Build context-aware system prompt
        from app.wealth.services.net_worth_calculator import NetWorthCalculator
        from app.wealth.ladder import detect_level
        
        net_worth = await NetWorthCalculator().calculate(user.id)
        level = detect_level(net_worth.total)
        
        system_prompt = REASONING_AGENT_SYSTEM_PROMPT.format(
            tool_descriptions=self._format_tool_descriptions(),
            name=user.display_name or "bạn",
            wealth_level=level.value,
            net_worth=f"{net_worth.total:,.0f}đ",
        )
        
        # Convert tools to Claude format
        claude_tools = self._to_claude_tools()
        
        messages = [{"role": "user", "content": query}]
        tool_calls_count = 0
        
        # Multi-round tool use loop
        while tool_calls_count < self.max_tool_calls:
            response = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                system=system_prompt,
                tools=claude_tools,
                messages=messages,
            )
            
            # Check if Claude wants to use a tool
            if response.stop_reason == "tool_use":
                # Find tool_use block
                tool_use_block = next(
                    b for b in response.content if b.type == "tool_use"
                )
                
                # Execute tool
                tool = self.registry.get(tool_use_block.name)
                if tool:
                    try:
                        validated_input = tool.input_schema(**tool_use_block.input)
                        result = await tool.execute(validated_input, user)
                        tool_result_content = result.model_dump_json()
                    except Exception as e:
                        tool_result_content = f"Error: {str(e)}"
                else:
                    tool_result_content = f"Unknown tool: {tool_use_block.name}"
                
                # Append to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": tool_result_content,
                    }],
                })
                
                tool_calls_count += 1
                continue
            
            # Final answer — stream it
            for block in response.content:
                if block.type == "text":
                    # Stream chunks for low latency UX
                    text = block.text
                    # Add disclaimer if not present
                    if "không phải lời khuyên đầu tư" not in text.lower():
                        text += "\n\n_Đây là gợi ý dựa trên data cá nhân, không phải lời khuyên đầu tư chuyên nghiệp._"
                    
                    await on_chunk(text)
            
            return  # Done
        
        # Max tool calls reached
        await on_chunk(
            "Mình cần thêm thông tin để trả lời chính xác. "
            "Bạn có thể hỏi cụ thể hơn được không?"
        )
    
    def _format_tool_descriptions(self):
        return "\n".join([
            f"- {t.name}: {t.description.split(chr(10))[0]}"
            for t in self.registry.list_all()
        ])
    
    def _to_claude_tools(self):
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema.model_json_schema(),
            }
            for t in self.registry.list_all()
        ]
```

**Why streaming via callback:** Telegram doesn't support true streaming, so we chunk messages. Callback pattern keeps streaming logic in agent + delivery logic in handler separate.

---

## 2.2 — Orchestrator (Heuristic + Cascade Routing)

### File: `content/router_heuristics.yaml`

```yaml
# Router heuristics for Phase 3.7
# Detect query type from keywords to route to correct tier.

# Keywords indicating Tier 2 (DB-Agent) — filter, sort, aggregate, compare
tier2_signals:
  filter:
    - "đang lãi"
    - "đang lỗ"
    - "trên \\d+"     # "trên 1 tỷ", "trên 100tr"
    - "dưới \\d+"
    - "lớn hơn"
    - "ít hơn"
    - "nhiều hơn"
  sort:
    - "top \\d+"
    - "nhiều nhất"
    - "ít nhất"
    - "lớn nhất"
    - "nhỏ nhất"
    - "cao nhất"
    - "thấp nhất"
  aggregate:
    - "tổng"
    - "trung bình"
    - "tỷ lệ"
    - "phần trăm"
    - "bao nhiêu phần trăm"
  compare:
    - "so với"
    - "vs"
    - "khác nhau"
    - "chênh lệch"
  list:
    - "liệt kê"
    - "show.*những"
    - "xem.*tất cả"

# Keywords indicating Tier 3 (Reasoning Agent) — advisory, what-if, planning
tier3_signals:
  should:
    - "có nên"
    - "nên không"
    - "có ổn không"
    - "phù hợp không"
  plan:
    - "làm thế nào để"
    - "lộ trình"
    - "kế hoạch"
    - "cần phải làm gì"
  what_if:
    - "nếu.*thì"
    - "nếu tôi"
    - "giả sử"
  advice:
    - "tư vấn"
    - "khuyên"
    - "gợi ý"
    - "recommend"
  why:
    - "tại sao"
    - "vì sao"
    - "do đâu"
```

### File: `app/agent/orchestrator.py`

```python
"""
Orchestrator: Routes queries to correct tier based on heuristics + cascade.
"""

import re
import yaml
from pathlib import Path

from app.intent.classifier.pipeline import IntentPipeline
from app.intent.dispatcher import IntentDispatcher
from app.intent.intents import IntentType
from app.agent.tools.base import ToolRegistry
from app.agent.tier2.db_agent import DBAgent
from app.agent.tier3.reasoning_agent import ReasoningAgent


class Orchestrator:
    def __init__(self):
        # Phase 3.5 components (Tier 1)
        self.intent_pipeline = IntentPipeline()
        self.intent_dispatcher = IntentDispatcher()
        
        # Build tool registry
        self.registry = self._build_registry()
        
        # Phase 3.7 components
        self.db_agent = DBAgent(self.registry)
        self.reasoning_agent = ReasoningAgent(self.registry)
        
        # Heuristics
        self.heuristics = self._load_heuristics()
    
    def _build_registry(self) -> ToolRegistry:
        from app.agent.tools.get_assets import GetAssetsTool
        from app.agent.tools.get_transactions import GetTransactionsTool
        from app.agent.tools.compute_metric import ComputeMetricTool
        from app.agent.tools.compare_periods import ComparePeriodsTool
        from app.agent.tools.get_market_data import GetMarketDataTool
        
        registry = ToolRegistry()
        registry.register(GetAssetsTool())
        registry.register(GetTransactionsTool())
        registry.register(ComputeMetricTool())
        registry.register(ComparePeriodsTool())
        registry.register(GetMarketDataTool())
        return registry
    
    def _load_heuristics(self):
        path = Path("content/router_heuristics.yaml")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    async def route(self, query: str, user, telegram_handler) -> str:
        """
        Main routing logic.
        Returns: response text (or sends streaming via telegram_handler for Tier 3)
        """
        
        # Step 1: Heuristic pre-route
        tier_hint = self._heuristic_classify(query)
        
        # Step 2: Route based on hint
        if tier_hint == "tier3":
            # Direct to reasoning (most expensive but justified)
            return await self._handle_tier3(query, user, telegram_handler)
        
        if tier_hint == "tier2":
            # Direct to DB-Agent
            return await self._handle_tier2(query, user)
        
        # Tier hint = "ambiguous" → cascade
        # Try Tier 1 (Phase 3.5) first
        intent_result = await self.intent_pipeline.classify(query)
        
        # Confidence check
        if intent_result.intent != IntentType.UNCLEAR and intent_result.confidence >= 0.8:
            # Phase 3.5 confident → use it
            return await self.intent_dispatcher.dispatch(intent_result, user)
        
        # Phase 3.5 not confident → escalate to Tier 2
        tier2_result = await self._handle_tier2(query, user)
        if tier2_result:
            return tier2_result
        
        # Tier 2 failed → escalate to Tier 3
        return await self._handle_tier3(query, user, telegram_handler)
    
    def _heuristic_classify(self, query: str) -> str:
        """Returns 'tier2', 'tier3', or 'ambiguous'."""
        q = query.lower()
        
        tier3_score = self._count_signals(q, self.heuristics["tier3_signals"])
        tier2_score = self._count_signals(q, self.heuristics["tier2_signals"])
        
        # Tier 3 wins if any reasoning signal (rare, distinct)
        if tier3_score >= 1:
            return "tier3"
        
        # Tier 2 wins if multiple DB signals OR strong single signal
        if tier2_score >= 1:
            return "tier2"
        
        return "ambiguous"
    
    def _count_signals(self, text: str, signals_dict: dict) -> int:
        count = 0
        for category_signals in signals_dict.values():
            for pattern in category_signals:
                if re.search(pattern, text):
                    count += 1
        return count
    
    async def _handle_tier2(self, query: str, user) -> str | None:
        from app.agent.tier2.formatters import format_db_agent_response
        
        result = await self.db_agent.answer(query, user)
        
        if not result.get("success"):
            return None  # Caller will escalate or fallback
        
        # Format response
        return await format_db_agent_response(result, user, query)
    
    async def _handle_tier3(self, query: str, user, telegram_handler) -> str:
        from app.agent.streaming.telegram_streamer import TelegramStreamer
        
        streamer = TelegramStreamer(telegram_handler)
        await streamer.start()  # Send typing indicator
        
        async def on_chunk(chunk: str):
            await streamer.send_chunk(chunk)
        
        try:
            await self.reasoning_agent.answer_streaming(query, user, on_chunk)
        except Exception as e:
            await streamer.send_chunk(
                "Mình gặp khó khăn trả lời câu này. Bạn thử cách khác xem?"
            )
        
        return ""  # Already sent via streamer
```

---

## 2.3 — Telegram Streaming

### File: `app/agent/streaming/telegram_streamer.py`

```python
"""
Stream responses to Telegram via chunked messages.
Telegram doesn't support true streaming, so we send chunks every ~500ms.
"""

import asyncio
from telegram import Update
from telegram.ext import ContextTypes


class TelegramStreamer:
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.update = update
        self.context = context
        self.buffer = ""
        self.last_flush_time = 0
        self.message_id = None  # ID of message being edited
        self.flush_interval = 0.8  # seconds
        self.min_chunk_size = 50  # chars
    
    async def start(self):
        """Send typing indicator + initial empty message."""
        await self.context.bot.send_chat_action(
            chat_id=self.update.effective_chat.id,
            action="typing",
        )
        # Send placeholder message
        msg = await self.update.message.reply_text("⏳ Đang phân tích...")
        self.message_id = msg.message_id
    
    async def send_chunk(self, text: str):
        """Add text to buffer, flush if conditions met."""
        self.buffer += text
        
        now = asyncio.get_event_loop().time()
        time_since_flush = now - self.last_flush_time
        
        if (
            len(self.buffer) >= self.min_chunk_size
            and time_since_flush >= self.flush_interval
        ):
            await self._flush()
    
    async def _flush(self):
        """Edit message with current buffer."""
        if not self.buffer:
            return
        
        try:
            await self.context.bot.edit_message_text(
                chat_id=self.update.effective_chat.id,
                message_id=self.message_id,
                text=self.buffer,
                parse_mode="Markdown",
            )
        except Exception as e:
            # Edit failed (rate limit?), send new message instead
            await self.update.message.reply_text(self.buffer, parse_mode="Markdown")
        
        self.last_flush_time = asyncio.get_event_loop().time()
    
    async def finish(self):
        """Final flush."""
        await self._flush()
```

**Why this approach:**
- Typing indicator engages user (Telegram native)
- Initial "⏳ Đang phân tích..." sets expectation
- Edit-in-place keeps chat clean
- Fallback to new message if rate limit hit
- Min chunk size avoids spam (don't edit every 5 chars)

---

## 2.4 — Cost & Latency Caps

### File: `app/agent/limits.py`

```python
"""
Hard limits to prevent runaway costs and timeouts.
"""

# Per-query limits
MAX_TOOL_CALLS_PER_QUERY = 5
MAX_TOTAL_TOKENS_PER_QUERY = 10000
QUERY_TIMEOUT_SECONDS = 30

# Per-user rate limits
MAX_TIER3_QUERIES_PER_HOUR = 10  # Premium queries are expensive
MAX_TOTAL_QUERIES_PER_HOUR = 100

# Cost monitoring
COST_ALERT_THRESHOLD_DAILY = 5.0  # USD
COST_HARD_LIMIT_DAILY = 20.0  # USD


class RateLimiter:
    """Simple Redis-based rate limiter."""
    
    async def check_tier3(self, user_id: int) -> bool:
        """Returns True if user can make Tier 3 query."""
        # Implementation using Redis sliding window
        # ...
        pass
    
    async def check_total(self, user_id: int) -> bool:
        """Returns True if user under total query limit."""
        pass
```

---

## ✅ Checklist Cuối Tuần 2

- [ ] Tier 3 ReasoningAgent working with Claude Sonnet
- [ ] Multi-tool calling loop with cap (max 5)
- [ ] Streaming via TelegramStreamer (typing indicator + chunks)
- [ ] Orchestrator routing correctly:
  - Heuristic detects tier 2 vs tier 3 vs ambiguous
  - Cascade fallback works (Phase 3.5 → Tier 2 → Tier 3)
- [ ] Rate limiting + cost caps in place
- [ ] Test: "Có nên bán FLC không?" → Tier 3 with multi-tool reasoning + streaming
- [ ] Test: "Tổng lãi portfolio" → Tier 2 single-tool

---

# 🎨 TUẦN 3: Polish + Audit + Testing

## 3.1 — Audit Logging

### File: `app/agent/audit.py`

```python
"""
Audit log for every agent invocation.
Critical for debugging, cost analysis, compliance.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, JSON, DateTime, Float, Boolean
from app.db.base import Base


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_logs"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    
    # Query info
    query_text = Column(String(2000))
    query_timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Routing
    tier_used = Column(String(20))  # "tier1", "tier2", "tier3"
    routing_reason = Column(String(100))  # "heuristic_tier2", "cascade_escalation"
    
    # Tool usage
    tools_called = Column(JSON)  # List of {name, args, latency_ms}
    tool_call_count = Column(Integer, default=0)
    
    # LLM usage
    llm_model = Column(String(50))
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Float)
    
    # Result
    success = Column(Boolean)
    response_preview = Column(String(500))  # First 500 chars
    error = Column(String(500), nullable=True)
    
    # Performance
    total_latency_ms = Column(Integer)
```

Every query → 1 audit log entry. Easy to:
- Find expensive queries
- Identify failing patterns
- Compute monthly cost
- Debug user complaints

---

## 3.2 — Caching Strategy

### File: `app/agent/caching.py`

```python
"""
Cache strategy for agent responses.
- Tier 2 (DB queries): cache 5 min, key by user_id + tool_name + args_hash
- Tier 3 (reasoning): cache 1 hour, key by user_id + query_hash
"""

import hashlib
import json
from redis.asyncio import Redis
from app.config import settings


class AgentCache:
    def __init__(self):
        self.redis = Redis.from_url(settings.REDIS_URL)
    
    async def get_tier2(self, user_id: int, tool_name: str, args: dict):
        key = self._tier2_key(user_id, tool_name, args)
        cached = await self.redis.get(key)
        return json.loads(cached) if cached else None
    
    async def set_tier2(self, user_id: int, tool_name: str, args: dict, result):
        key = self._tier2_key(user_id, tool_name, args)
        await self.redis.setex(
            key,
            300,  # 5 min
            json.dumps(result),
        )
    
    async def get_tier3(self, user_id: int, query: str):
        key = self._tier3_key(user_id, query)
        cached = await self.redis.get(key)
        return cached.decode() if cached else None
    
    async def set_tier3(self, user_id: int, query: str, response: str):
        key = self._tier3_key(user_id, query)
        await self.redis.setex(key, 3600, response)  # 1 hour
    
    def _tier2_key(self, user_id, tool_name, args):
        args_hash = hashlib.md5(
            json.dumps(args, sort_keys=True).encode()
        ).hexdigest()[:8]
        return f"agent:t2:{user_id}:{tool_name}:{args_hash}"
    
    def _tier3_key(self, user_id, query):
        query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]
        return f"agent:t3:{user_id}:{query_hash}"
```

---

## 3.3 — Integration với Phase 3.5 Free-Form Handler

Update `app/bot/handlers/free_form_text.py`:

```python
async def handle_free_form_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = await user_service.get_by_telegram_id(user_id)
    
    # NEW: Route through Orchestrator
    from app.agent.orchestrator import Orchestrator
    orchestrator = Orchestrator()
    
    response = await orchestrator.route(text, user, telegram_handler=(update, context))
    
    if response:  # Tier 1/2 returns text
        await update.message.reply_text(response, parse_mode="Markdown")
    # Tier 3 streams directly via TelegramStreamer
```

---

## 3.4 — Test Suite

### Test fixture queries

`tests/test_agent/fixtures/tier_test_queries.yaml`:

```yaml
# Test queries with expected tier + behavior
queries:
  # === Tier 2 (DB-Agent) ===
  - query: "Mã chứng khoán nào của tôi đang lãi?"
    expected_tier: "tier2"
    expected_tool: "get_assets"
    expected_filter: {asset_type: "stock", gain_pct: {gt: 0}}
  
  - query: "Liệt kê các mã chứng khoán tôi đang lỗ"
    expected_tier: "tier2"
    expected_tool: "get_assets"
    expected_filter: {asset_type: "stock", gain_pct: {lt: 0}}
  
  - query: "Top 3 mã lãi nhiều nhất"
    expected_tier: "tier2"
    expected_tool: "get_assets"
    expected_sort: "gain_pct_desc"
    expected_limit: 3
  
  - query: "Tổng lãi portfolio của tôi"
    expected_tier: "tier2"
    expected_tool: "compute_metric"
    expected_metric: "portfolio_total_gain"
  
  - query: "Chi cho ăn uống tuần này so với tuần trước"
    expected_tier: "tier2"
    expected_tool: "compare_periods"
  
  # === Tier 3 (Reasoning) ===
  - query: "Có nên bán FLC để cắt lỗ không?"
    expected_tier: "tier3"
    expected_min_tools_called: 1
  
  - query: "Làm thế nào để đạt mục tiêu mua xe trong 2 năm?"
    expected_tier: "tier3"
  
  - query: "Nếu tôi giảm chi 20% thì tiết kiệm thêm bao nhiêu/năm?"
    expected_tier: "tier3"
  
  # === Tier 1 (Phase 3.5 unchanged) ===
  - query: "Tài sản của tôi có gì?"
    expected_tier: "tier1"
  
  - query: "VNM giá bao nhiêu?"
    expected_tier: "tier1"
```

### Critical Test: The Original Bug

**MUST PASS:**

```python
async def test_winners_query_returns_only_winners():
    """Phase 3.5 bug: query 'mã đang lãi' returned ALL stocks."""
    user = create_test_user_with_mixed_portfolio()
    # Portfolio: VNM +10%, HPG -5%, NVDA +20%, FPT -3%
    
    orchestrator = Orchestrator()
    response = await orchestrator.route(
        "Mã chứng khoán nào của tôi đang lãi?",
        user,
        telegram_handler=mock_handler(),
    )
    
    assert "VNM" in response
    assert "NVDA" in response
    assert "HPG" not in response  # Loser, must NOT appear
    assert "FPT" not in response
```

This is **the exit criteria test**. If this fails, Phase 3.7 isn't done.

---

## ✅ Checklist Cuối Tuần 3

- [ ] Audit logging on all agent invocations
- [ ] Cache reduces Tier 2 calls (cache hit rate ≥30%)
- [ ] Cache reduces Tier 3 calls (>50% cache hits for repeat queries)
- [ ] Integration with free_form_text handler (Phase 3.5)
- [ ] Test fixture file with 30+ queries
- [ ] **CRITICAL TEST: Winners query returns only winners** ✅
- [ ] User testing with 3 personas (Hà, Phương, Anh Tùng)
- [ ] Cost projection verified: avg <$0.001/query
- [ ] Latency p95 <5s for Tier 2, <10s for Tier 3
- [ ] Documentation updated

---

# 📊 Metrics Phase 3.7

Track from Day 1:

**Coverage:**
- % queries answered correctly (target: ≥90%)
- % queries from each tier (Tier 1 ~60%, Tier 2 ~30%, Tier 3 ~10%)

**Quality:**
- Tier 2 tool selection accuracy (target: ≥95%)
- Tier 3 response satisfaction (user thumbs up rate)
- Filter/sort correctness on test fixtures

**Cost:**
- Average cost per query (target: <$0.001)
- Tier 3 cost share (target: <60% of total)
- Cache hit rate (target: ≥40%)

**Performance:**
- Tier 2 latency p95 (target: <5s)
- Tier 3 latency p95 (target: <10s)
- Streaming first chunk latency (target: <2s)

---

# 🎯 Exit Criteria Phase 3.7

Phase 3.7 ready to ship when:

- [ ] **CRITICAL: "Mã đang lãi?" returns only winners** (the original bug fix)
- [ ] All 5 tools functional with unit tests
- [ ] Orchestrator routes correctly on 30+ test queries
- [ ] Tier 2 average latency <3s
- [ ] Tier 3 streaming feels responsive (<2s first chunk)
- [ ] Cost under budget ($25/month at current usage)
- [ ] No regressions in Phase 3.5 (Tier 1 still works)
- [ ] No regressions in Phase 3.6 menu
- [ ] User testing positive (≥3 users)
- [ ] Audit log + cost dashboard working
- [ ] Documentation complete

---

# 🚧 Bẫy Thường Gặp Phase 3.7

## 1. Tool schemas too loose
LLM picks wrong args. Fix: Use Pydantic with strict types + Literal types where possible.

## 2. Heuristics too aggressive
Mọi query "tài sản" → Tier 2 even simple ones. Fix: Tune heuristics, prefer Tier 1 when ambiguous.

## 3. Tier 3 infinite loop
LLM keeps calling tools, never composes answer. Fix: Hard cap MAX_TOOL_CALLS=5.

## 4. Streaming feels janky
Updates too frequent → rate limit. Updates too rare → user thinks bot stuck. Fix: 0.8s flush interval.

## 5. Cost spike from Tier 3
1 user queries Tier 3 50 times/day = $$. Fix: Per-user rate limit.

## 6. Filter not strict
LLM extracts `gain_pct: 0` instead of `gain_pct > 0`. Fix: Detailed examples in tool description.

## 7. Cache invalidation
User adds asset, cache still returns old data. Fix: Cache key includes asset hash, invalidate on writes.

## 8. Audit log slow
Logging blocks main path. Fix: Async fire-and-forget logging.

---

**Phase 3.7 transforms Bé Tiền into a true AI agent. After this phase, adding new capabilities = adding new tools. No architectural rework needed for Phase 4+. 🚀💚**
