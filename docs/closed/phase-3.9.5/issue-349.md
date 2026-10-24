# Issue #349

[Story] P3.9.5-S11: Cổ phiếu — bảng giá portfolio + query CK theo mã

**Parent Epic:** #337 (Epic 4: Thị trường)

## Description
Bảng giá hiện show all stocks (overwhelming). Pattern mới: filtered theo portfolio user.

## Acceptance Criteria
- [ ] Default view "Bảng giá" filtered theo user.portfolio.stocks
- [ ] Empty portfolio → hint "Thêm CK vào portfolio để theo dõi"
- [ ] Button "🔍 Tìm CK theo mã" → user gõ mã (VNM) → show quote
- [ ] Query path dùng SSI provider từ Phase 3.9
- [ ] Cache 5 phút
- [ ] Invalid ticker → friendly error

## Estimate: ~0.5 day
## Dependencies: None

Close #337
