# Issue #433

[Story] P4B-S16: 3-Month Cashflow Forecast Model

**Parent Epic:** #416 (Epic 3: Cashflow Forecasting v2)

## User Story
Toi muon biet thang toi va 2 thang nua du kien co bao nhieu tien.

## Implementation Tasks
- [ ] Alembic migration: cashflow_forecasts table
- [ ] cashflow/forecast.py: compute_cashflow_forecast() with confirmed patterns
- [ ] Adjust for actuals current month
- [ ] Low-balance threshold: default = avg monthly expense
- [ ] Cron daily 01:00 AM

## Estimate: ~1 day
## Depends on: P4B-S14, P4B-S15

Close #416
