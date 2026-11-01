# Issue #183

[Story] P3.7-S1: Define tool schemas with Pydantic

**Parent Epic:** #180 (Epic 1: Tool Foundation & DB-Agent)

## User Story
As a developer building agent tools, I need typed Pydantic schemas cho tất cả tool inputs/outputs so LLM gets clear JSON schemas, validation prevents bad calls, và tests have reusable models.

## Tại Sao Story Này Đến Trước
Schemas shape capability. Loose schemas → LLM picks wrong args → bugs. Strict typed schemas → LLM picks correct args → success. **Time invested here saves debugging later.**

## Acceptance Criteria
- [ ] File `app/agent/tools/schemas.py` exists
- [ ] **Enums:**
  - `AssetType`: stock, real_estate, crypto, gold, cash
  - `SortOrder`: value_asc/desc, gain_asc/desc, gain_pct_asc/desc, name, created_desc
  - `TransactionCategory`: food, transport, housing, shopping, health, education, entertainment, utility, gift, investment
  - `MetricName`: saving_rate, net_worth_growth, portfolio_total_gain, average_monthly_expense, expense_to_income_ratio, diversification_score
- [ ] **Filter models:**
  - `NumericFilter` với gt/gte/lt/lte/eq
  - `AssetFilter` (asset_type, ticker, value, gain_pct)
  - `TransactionFilter` (category, date range, amount)
- [ ] **Tool input models** (5):
  - `GetAssetsInput` (filter, sort, limit)
  - `GetTransactionsInput` (filter, sort, limit)
  - `ComputeMetricInput` (metric_name, period_months)
  - `ComparePeriodsInput` (metric, period_a, period_b)
  - `GetMarketDataInput` (ticker, period)
- [ ] **Tool output models** (5): `GetAssetsOutput`, `GetTransactionsOutput`, `MetricResult`, `ComparisonResult`, `MarketDataPoint`
- [ ] Tất cả schemas có **descriptive Field() descriptions** (LLM dùng để chọn đúng)
- [ ] `model_json_schema()` không errors
- [ ] **Decimal dùng cho money (không float)**
- [ ] Type checks pass (mypy strict)

## Test Plan
```python
def test_schemas_serialize():
    schema = GetAssetsInput.model_json_schema()
    assert "filter" in schema["properties"]

def test_decimal_for_money():
    item = AssetItem(name="VNM", current_value=Decimal("1000000"))
    assert isinstance(item.current_value, Decimal)
```

## Estimate: ~1 day
## Depends on: None
## Reference: `docs/current/phase-3.7-detailed.md` § 1.1
