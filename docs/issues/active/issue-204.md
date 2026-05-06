# Issue #204

[Epic] Phase 3.8 — Epic 1: Rental Property Tracking

## Phase 3.8 — Epic 1: Rental Property Tracking

> **Type:** Epic | **Week:** 1 | **Stories:** 3

## Context
Phase 3.8 là **"Wealth Completion"** — fill gaps về data trước khi Phase 4 (Twin) build predictions. Epic 1 cover BĐS cho thuê (Case A — chủ nhà), không phải nhà thuê ở (Case B).

## Tại Sao Epic Này Quan Trọng
Mass Affluent users thường có ≥1 BĐS cho thuê. Hiện tại net worth chỉ show **static value** — bỏ sót active income generation. Epic này fix gap đó.

## Success Definition
- ✅ User mark real_estate asset là rental (trong wizard hoặc sau)
- ✅ Update occupancy status (rented / vacant / self-use)
- ✅ Reports show "passive income from rentals" riêng biệt
- ✅ Annual yield % tính tự động
- ✅ Phase 3.7 agent query được: "BĐS nào đang cho thuê?", "thu nhập từ BĐS"

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.8-S1: Extend Asset model with rental fields
- [ ] [Story] P3.8-S2: Build RentalService + business logic
- [ ] [Story] P3.8-S3: Update asset wizard to capture rental data

## Note
Epic 1, 2, 3 có thể chạy **song song** trong Tuần 1 — không depend nhau.

## Reference
`docs/current/phase-3.8/phase-3.8-detailed.md` § 1.1
