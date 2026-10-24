# Issue #678

[Story 2.2] Story Narrative Flow (Swipe-Through Screens) — Phase 4.3

## Story 2.2 — Story Narrative Flow (Swipe-Through Screens)

**Parent Epic:** #671 | **Estimate:** 1.5 days | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Stories 1.1 (#674), 1.2 (#675), 2.1 (#677)

### User Story
> Là một mass affluent user xem Twin lần đầu, tôi muốn được dẫn dắt qua một câu chuyện: "đây là hiện tại → tương lai có thể → vì sao → anh có thể làm gì". Sau đó nếu muốn, tôi mới xem chart.

### Requirements
- [ ] 5 screens với Telegram inline keyboard navigate forward/back
- [ ] Skip: "Bỏ qua, xem nhanh" → jump to Screen 5
- [ ] Subsequent views: compact (Screen 2 + 5 condensed)
- [ ] Full flow re-show: nếu user request hoặc sau 30 ngày
- [ ] Migration 4.3.02: `twin_view_events` table

### Files Touched
- `apps/twin_renderer/flows/first_time_view.py` (new)
- `apps/twin_renderer/views/narrative_screen_*.py` (new)
- `apps/twin_renderer/views/twin_viewer.py` (modify)
- `db/migrations/4.3.02_twin_view_events.sql` (new)

### Definition of Done
- [ ] All AC met
- [ ] Analytics logging verified
- [ ] PR closes #678

