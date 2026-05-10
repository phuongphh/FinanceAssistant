# Issue #351

[Story] P3.9.5-S13: BUG — "Portfolios của tôi" trong Tiền số nhảy sang Chứng khoán

**Parent Epic:** #337 (Epic 4: Thị trường)

## ⚠️ P1 Bug — Highest Priority

## Description
Action ("market", "crypto", "portfolio") dispatch sai → mở stock portfolio thay vì crypto. Blocking crypto Portfolios hoàn toàn.

## Acceptance Criteria
- [ ] Reproduce bug, log dispatch path
- [ ] Fix routing: crypto portfolio → QUERY_PORTFOLIO với asset_type: "crypto" (không default "stock")
- [ ] Regression: click crypto portfolio → response chứa coins, không phải stocks
- [ ] Audit Vàng portfolio (same pattern, no bug)
- [ ] Audit BĐS portfolio nếu có

## Estimate: ~0.5 day
## Dependencies: None — SHIP DAY 1

Close #337
