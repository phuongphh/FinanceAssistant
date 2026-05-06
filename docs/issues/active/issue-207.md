# Issue #207

[Epic] Phase 3.8 — Epic 4: Cashflow Forecasting (Simple v1)

## Phase 3.8 — Epic 4: Cashflow Forecasting (Simple v1)

> **Type:** Epic | **Week:** 2 | **Stories:** 2

## Tại Sao Epic Này Quan Trọng
**"Cashflow Forecast = Twin Foundation"** — forecasting v1 này là seed cho Phase 4 Twin projections. Build đúng từ đầu, Phase 4 mở rộng không cần redesign.

## Methodology
- Baseline: average last 3 months income + expense
- Add: known recurring (high confidence)
- Add: scheduled income (salary day, dividend dates)
- Confidence decay: Month 1=85%, Month 2=70%, Month 3=55%

## Success Definition
- ✅ User hỏi "tháng tới tiết kiệm bao nhiêu?" → forecast shown với confidence
- ✅ Runway analyzer warns nếu liquid assets <3 tháng expenses
- ✅ Phase 3.7 agent có `forecast_cashflow` tool mới

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.8-S11: CashflowForecaster + RunwayAnalyzer
- [ ] [Story] P3.8-S12: ForecastCashflow tool integration

## Dependencies
✅ Epic 2 (income data) + Epic 3 (recurring data) complete

## Reference
`docs/current/phase-3.8/phase-3.8-detailed.md` § 2.1
