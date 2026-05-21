# Issue #420

[Story] P4B-S3: LLM Narrative v2

**Parent Epic:** #414 (Epic 1: Twin Polish)

## User Story
Tôi muốn Bé Tiền nói về tương lai của TÔI, không phải câu chung chung.

## Implementation Tasks
- [ ] Thêm wealth_level + top_asset_changes_30d + life_events context vào LLM prompt
- [ ] Cập nhật few-shot examples: loại bỏ generic phrases
- [ ] Chạy prompt-tester agent trước merge

## Acceptance Criteria
- [ ] Narrative khác nhau giữa Khởi Đầu vs Tinh Hoa
- [ ] Nếu có life events → nhắc ≥1 event cụ thể với số tiền
- [ ] Không có generic: "tương lai tài chính của bạn", "bạn đang đi đúng hướng"

## Estimate: ~0.5 day
## Dependencies: Phase 4A LLM narrative ✅

Close #414
