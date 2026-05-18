# Issue #678

[Story 2.2] Story Narrative Flow (Swipe-Through Screens) — Phase 4.3

## Story 2.2 — Story Narrative Flow (Swipe-Through Screens)

**Parent Epic:** #671 | **Estimate:** 1.5 days | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Stories 1.1, 1.2, 2.1

### User Story
> Là một mass affluent user xem Twin lần đầu, tôi muốn được dẫn dắt qua một câu chuyện: "đây là hiện tại → tương lai có thể → vì sao → anh có thể làm gì". Sau đó nếu muốn, tôi mới xem chart.

### Requirements
- [ ] 5 screens với Telegram inline keyboard navigate forward/back:
  - Screen 1: Present (anchor + delta)
  - Screen 2: Future Range (3 weather cards + life outcome)
  - Screen 3: Causality summary (Story 3.2 brief)
  - Screen 4: Action suggestion preview (Story 3.3 entry)
  - Screen 5: "📊 Xem chart kỹ thuật" + "Đặt mục tiêu ngay"
- [ ] Forward: "Tiếp tục →" / "Quay lại ←"
- [ ] Skip: "Bỏ qua, xem nhanh" → jump to Screen 5
- [ ] Subsequent views: compact (Screen 2 + 5 condensed)
- [ ] Full flow re-show: nếu user request "Xem chi tiết" hoặc sau 30 ngày
- [ ] Migration 4.3.02: `twin_view_events` table

### Files Touched
- `apps/twin_renderer/flows/first_time_view.py` (new)
- `apps/twin_renderer/views/narrative_screen_*.py` (new)
- `apps/twin_renderer/views/twin_viewer.py` (modify)
- `db/migrations/4.3.02_twin_view_events.sql` (new)

### Claude Code Implementation Prompt
```
Implement Story 2.2 of Epic #671 (Phase 4.3):
Story Narrative Flow (Swipe-Through Screens)

PR should close #[ISSUE_NUMBER]
```

