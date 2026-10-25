# Issue #65

[P3A-7] Build Asset Entry Wizard: Stock flow

## Epic
Epic 1 — Asset Data Model | **Week 1** | Depends: P3A-3 | Blocks: P3A-9

## Description
Wizard 3-4 bước cho stock/fund asset.

## Acceptance Criteria
- [ ] Handler `start_stock_wizard()` — ask ticker
- [ ] Handler `handle_stock_ticker()` — validate, save metadata.ticker
- [ ] Handler `handle_stock_quantity()` — ask quantity, validate integer
- [ ] Handler `handle_stock_price()` — ask avg price
- [ ] Handler `handle_stock_current_price()` — offer "same as avg" hoặc nhập mới
- [ ] Save metadata: `{"ticker": "VNM", "quantity": 100, "avg_price": 45000, "exchange": "HOSE"}`
- [ ] Support subtypes: vn_stock, fund, etf, foreign_stock
- [ ] Edge case: ticker không tồn tại → vẫn cho save (Phase 3B validate)
- [ ] Edge case: "VNM stocks" → normalize về "VNM"

## Technical Notes
- `initial_value = quantity * avg_price`
- `current_value = quantity * current_price`
- Phase 3B sẽ auto-update từ market

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.6 — Stock Wizard
