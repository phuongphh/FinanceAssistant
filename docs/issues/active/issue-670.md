# Issue #670

[Epic 1] Twin Comprehension Foundation — Phase 4.3

## 📌 Epic 1: Twin Comprehension Foundation

**Phase:** 4.3 | **Estimate:** 5 days | **Priority:** P0 | **Surface:** Telegram

### Goal
User tap vào Twin lần đầu hiểu được "đây là điều gì" trong < 30 giây, không cần đọc giải thích dài.

### Description
Mass affluent VN không có background statistics → P10/P50/P90 = jargon. Epic này thay clothing của Twin: từ probability cone → weather metaphor; từ raw number tỷ VND → life outcome dễ hình dung; từ "future projection" → "present + đang đi đâu". Không thay compute layer (Phase 4A Monte Carlo giữ nguyên).

### Success Criteria
- [ ] 5/5 dogfood tester (non-finance background) giải thích đúng Twin trong < 2 phút sau khi xem lần đầu
- [ ] Twin first-view → 2nd-view conversion ≥ 50% trong cohort 14 ngày đầu
- [ ] 0 P0 regression: math output Twin viz vẫn match Phase 4A Monte Carlo within tolerance 0.5%

### Stories
- **1.1** Rename P10/P50/P90 → Weather Vocabulary (1d, P0)
- **1.2** Life Outcome Translation via LLM (2d, P0, depends on 1.1)
- **1.3** Present Anchor + Delta + Growth Rate Display (2d, P0, depends on 1.1)

