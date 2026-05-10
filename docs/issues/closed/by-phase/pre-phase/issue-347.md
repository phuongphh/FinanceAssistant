# Issue #347

[Story] P3.9.5-S9: Thêm báo cáo "Dòng tiền tháng này"

**Parent Epic:** #336 (Epic 3: Dòng tiền)

## Description
User muốn 1 báo cáo deep-dive cho tháng hiện tại (không phải Tổng quan compare nhiều tháng).

## Acceptance Criteria
- [ ] Button mới "📅 Dòng tiền tháng này" trong submenu Cashflow
- [ ] Action key ("cashflow", "monthly_report") → IntentType.QUERY_CASHFLOW với focus: "current_month_detail"
- [ ] Report: Tổng thu/tổng chi/net flow, top 3 income sources, top 3 expense categories, daily flow chart, biggest 3 transactions
- [ ] Vietnamese copy qua content/menu_copy.yaml
- [ ] Render < 2s

## Estimate: ~0.5 day
## Dependencies: S6, S7

Close #336
