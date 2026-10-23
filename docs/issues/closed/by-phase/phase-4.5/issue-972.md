# Issue #972

[Phase 4.5 / E1] 1.2 — liquidation_advisor.rank_options()

`backend/services/decision/liquidation_advisor.py` — per asset type user sở hữu: tác động rút lên quỹ đạo + thanh khoản → xếp hạng ít-hại-nhất. **Options sinh từ portfolio query — không có code path recommend sản phẩm ngoài** (ranh giới pháp lý).

**DoD:**
- [ ] Unit test ranking với 3 portfolio shape
- [ ] Test user chỉ có 1 loại tài sản
- [ ] Test amount > tổng thanh khoản → nói thật "không đủ"

Epic: #959 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
