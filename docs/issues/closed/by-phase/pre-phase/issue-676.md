# Issue #676

[Story 1.3] Present Anchor + Delta + Growth Rate — Phase 4.3

## Story 1.3 — Present Anchor + Delta + Growth Rate Display

**Parent Epic:** #670 | **Estimate:** 2 days | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Story 1.1 (#674)

### User Story
> Là một mass affluent user, tôi không chỉ muốn biết "tôi sẽ có gì năm 2030", tôi cần thấy "tôi đang có gì BÂY GIỜ và tốc độ đang đi như thế nào".

### Requirements
- [ ] Twin viewer screen có 3 elements ở top:
  - **Present anchor:** "Hiện tại: 850tr" — current net worth tính real-time
  - **Weekly delta:** "↑ Tăng 12tr" hoặc "↓ Giảm 8tr" với arrow (↑ green, ↓ amber)
  - **Growth rate:** "Tốc độ ~ 50tr/tháng" — rolling 90-day average
- [ ] Delta zero/very small: hiển thị "Ổn định"
- [ ] Growth rate chưa đủ data (< 30 ngày): "Đang theo dõi nhịp"
- [ ] Tap vào present anchor → expand net worth breakdown
- [ ] Tap vào delta → trigger causality breakdown (Story 3.2)
- [ ] Tap vào growth rate → show "Nếu duy trì, năm 2030 có thể đạt ⛅ X tỷ"

### Files Touched
- `apps/twin_renderer/views/present_anchor.py` (new)
- `apps/twin_renderer/services/growth_rate_calculator.py` (new)
- `apps/twin_renderer/views/twin_viewer.py` (modify)

### Definition of Done
- [ ] All AC met
- [ ] Edge cases handled (new user, negative net worth, large volatility)
- [ ] PR closes #676

