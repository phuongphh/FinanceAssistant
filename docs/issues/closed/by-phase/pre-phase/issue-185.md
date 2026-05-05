# Issue #185

[Story] P3.7-S3: Implement ComputeMetric, ComparePeriods, GetMarketData tools

**Parent Epic:** #180 (Epic 1: Tool Foundation & DB-Agent)

## User Story
As an agent answering aggregate/comparison/market queries, tôi cần 3 tools còn lại để user hỏi "Tổng lãi portfolio?", "Tháng này vs tháng trước?", "VNM giá?".

## Acceptance Criteria

### ComputeMetricTool (`app/agent/tools/compute_metric.py`):
- [ ] Accepts metric_name + period_months
- [ ] Implements: saving_rate, net_worth_growth, portfolio_total_gain, average_monthly_expense, expense_to_income_ratio
- [ ] Returns `MetricResult` với value, unit, context
- [ ] Reuses Phase 3A/3.5 calculation logic where exists

### ComparePeriodsTool (`app/agent/tools/compare_periods.py`):
- [ ] Accepts metric (expenses/income/net_worth/savings) + period_a + period_b
- [ ] Computes diff_absolute và diff_percent
- [ ] Returns `ComparisonResult`
- [ ] Handles edge case: period có no data

### GetMarketDataTool (`app/agent/tools/get_market_data.py`):
- [ ] Accepts ticker + period
- [ ] Calls Phase 3.5 MarketService
- [ ] **Adds personal context** nếu user owns ticker (quantity, holding_value)
- [ ] Returns `MarketDataPoint`
- [ ] Handles unknown ticker gracefully
- [ ] Stub OK nếu Phase 3B chưa done (với note)

### General:
- [ ] **Tất cả 3 tools registered trong ToolRegistry**
- [ ] Test scenarios:
  - ComputeMetric: saving_rate cho test user → reasonable %
  - ComparePeriods: this_month vs last_month → diff calculated
  - GetMarketData: VNM → price + user holding info
- [ ] Mỗi tool: ≥3 realistic test cases

## Estimate: ~1.5 day
## Depends on: P3.7-S1 (parallel với S2)
## Reference: `docs/current/phase-3.7-detailed.md` § 1.2
