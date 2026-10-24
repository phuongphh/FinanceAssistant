# Issue #64

[P3A-6] Build Asset Entry Wizard: Cash flow

## Epic
Epic 1 — Asset Data Model | **Week 1** | Depends: P3A-3 | Blocks: P3A-9

## Description
Wizard đơn giản nhất (2 câu hỏi) cho cash asset. Entry wizard — phần lớn users bắt đầu với cash.

## Acceptance Criteria
- [ ] Handler `start_cash_wizard()` — show subtype buttons (bank_savings, bank_checking, cash, e_wallet)
- [ ] Handler `handle_cash_subtype()` — save subtype, ask name + amount
- [ ] Handler `handle_cash_text_input()` — parse flexible:
  - "VCB 100 triệu"
  - "Techcom 50tr"
  - "MoMo 2tr"
  - "Tiết kiệm 500 nghìn"
- [ ] Save asset với source="user_input"
- [ ] Show confirmation + net worth update
- [ ] Offer "Thêm tài sản khác" button
- [ ] Validation: reject số âm, zero
- [ ] Error handling: parse fail → ask lại ấm áp

## Technical Notes
- Reuse `parse_transaction_text` từ Phase 3 cũ (amount parsing)
- Context state trong `context.user_data["asset_draft"]`

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.6 — Cash Wizard
