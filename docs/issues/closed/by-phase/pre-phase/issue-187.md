# Issue #187

[Story] P3.7-S5: Implement Tier 2 response formatters

**Parent Epic:** #180 (Epic 1: Tool Foundation & DB-Agent)

## User Story
As a user nhận result của "Mã đang lãi?", tôi muốn beautifully formatted response — list winning stocks với current price, gain, percentage — trong Bé Tiền warm tone.

## Acceptance Criteria
- [ ] File `app/agent/tier2/formatters.py` với `format_db_agent_response()`
- [ ] Format functions cho từng tool:
  - `format_assets_response()` — list với gain indicators (🟢 gain >0, 🔴 loss)
  - `format_transactions_response()` — chronological list
  - `format_metric_response()` — metric value + context
  - `format_comparison_response()` — side-by-side comparison
  - `format_market_response()` — price + change + personal context
- [ ] **Wealth-level adaptive** (reuse Phase 3.5 logic):
  - Starter: simple language
  - HNW: detailed, professional
- [ ] **Empty state handling:**
  - 0 results → friendly: "Không có mã nào đang lãi 🤔"
  - 0 assets → suggest "/add_asset"
- [ ] **Bé Tiền personality:** greeting variation, suggestion at end, user name
- [ ] **Inline keyboard** cho follow-up actions khi relevant
- [ ] Test: same query 3 lần → variation in opening, same data
- [ ] Reuse `format_money_short()`, `format_money_full()` từ Phase 1

## Sample Output
```
✨ Mã chứng khoán đang lãi của Hà:

🟢 NVDA — 6.2 tỷ (+4.2%)
🟢 VHM — 5.4 tỷ (+80%)
🟢 VIC — 1.7 tỷ (+142.9%)

Tổng giá trị: 13.3 tỷ

[💡 Xem mã đang lỗ] [📈 Báo cáo chi tiết]
```

## Estimate: ~1 day
## Depends on: P3.7-S4
## Reference: `docs/current/phase-3.7-detailed.md` § 1.3
