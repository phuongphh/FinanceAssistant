# Issue #681

[Story 3.3] Action Suggestion Embedded in Twin Flow — Phase 4.3

## Story 3.3 — Action Suggestion Embedded in Twin Flow

**Parent Epic:** #672 | **Estimate:** 1 day | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Story 3.2

### User Story
> Là một mass affluent user vừa hiểu vì sao Twin thay đổi, tôi muốn 1 gợi ý cụ thể, doable trong 5 phút — không phải lời khuyên chung chung.

### Requirements
- [ ] Action library `action_suggestion.yaml` với key (state_segment, delta_direction, has_goal)
- [ ] Service `twin_action_suggestion_service.suggest(user_context, delta_info)` → ActionSuggestion
- [ ] Each suggestion ≤ 5 phút với deep_link
- [ ] Card format: title, description ≤ 2 câu, time_estimate, buttons
- [ ] Logged vào `twin_action_suggestions` (Migration 4.3.04)
- [ ] "Đặt mục tiêu ngay" → execute inline
- [ ] "Để tôi suy nghĩ thêm" → reminder 48h
- [ ] Repeat suppression: cùng type dismissed 3 lần → skip 30 ngày
- [ ] Variety: không suggest cùng type 2 lần liên tiếp trong 7 ngày

### Files Touched
- `apps/twin_renderer/services/action_suggestion_service.py` (new)
- `content/twin/action_suggestion.yaml` (new, ~30-50 templates)
- `db/migrations/4.3.04_twin_action_suggestions.sql` (new)

### Claude Code Implementation Prompt
```
Implement Story 3.3 of Epic #672 (Phase 4.3):
Action Suggestion Embedded in Twin Flow

PR should close #[ISSUE_NUMBER]
```

