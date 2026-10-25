# Issue #219

[Story] P3.8-S11: CashflowForecaster + RunwayAnalyzer

**Parent Epic:** #207 (Epic 4: Cashflow Forecasting Simple v1)

## User Story
As a user, tôi muốn hỏi "tháng tới tiết kiệm bao nhiêu?" và nhận forecast với confidence level — không phải generic advice.

## Methodology
- Baseline: average last 3 months income + expense
- Layer in: known recurring (high confidence)
- Layer in: scheduled income (salary day, dividend)
- Confidence decay: M1=85%, M2=70%, M3=55%

## Acceptance Criteria
- [ ] `CashflowForecaster` class:
  - `forecast(user_id, months_ahead=3)` → list of `MonthlyForecast`
  - Each: month, expected_income, expected_expense, expected_savings, confidence, breakdown, notes
- [ ] `RunwayAnalyzer` class:
  - `compute_runway(user_id)` → dict: months, liquid_assets, monthly_burn, warning
  - Liquid assets = cash + savings accounts (**không** phải stocks/BĐS — illiquid)
  - Essential expenses = recurring patterns + base average
  - Warnings: <3 tháng ("🚨"), 3-6 tháng ("⚠️"), >6 tháng (no warning)
- [ ] Edge cases:
  - <3 tháng data → dùng available, mark low confidence
  - 0 income tracked → forecast từ expenses only, warn user
  - 0 expenses tracked → forecast just income
- [ ] Test scenarios:
  - User stable: forecast ±10% reality
  - User với rental income: forecast includes 15tr/tháng
  - User với quarterly dividend: forecast spikes đúng tháng

## Estimate: ~1.5 day
## Depends on: Epic 2 (income) + Epic 3 (recurring) complete
