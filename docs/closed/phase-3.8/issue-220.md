# Issue #220

[Story] P3.8-S12: ForecastCashflow tool + agent integration

**Parent Epic:** #207 (Epic 4: Cashflow Forecasting Simple v1)

## User Story
As the Phase 3.7 agent, I need a `forecast_cashflow` tool để trả lời queries về dự đoán tương lai.

## Acceptance Criteria
- [ ] File `app/agent/tools/forecast_cashflow.py`
- [ ] Tool description với examples:
  - "tháng tới tôi tiết kiệm bao nhiêu?" → forecast 1 month
  - "dự đoán cashflow 3 tháng tới" → forecast 3 months
  - "bao giờ tôi âm tài khoản?" → runway analysis
- [ ] Input schema: `months_ahead` (1-12), `include_runway` (bool)
- [ ] Output: forecast list + optional runway info
- [ ] Registered trong ToolRegistry
- [ ] **Response formatter:**
  - Monthly breakdown với emoji: 📈 income, 📉 expense, 💎 savings
  - Confidence level displayed
  - Runway warning nếu có → prominent display
- [ ] **Critical test:** "Tháng 7 dự kiến tiết kiệm bao nhiêu?" → specific number với confidence %

## Estimate: ~0.5 day
## Depends on: P3.8-S11
