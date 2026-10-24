# Issue #684

[Story 3.6] Return Tease + Loop Closure — Phase 4.3

## Story 3.6 — Return Tease + Loop Closure

**Parent Epic:** #672 | **Estimate:** 1 day | **Priority:** P1 | **Surface:** Telegram | **Depends on:** Story 3.3

### User Story
> Là một mass affluent user vừa execute action, tôi muốn biết khi nào quay lại có ý nghĩa — "sáng mai check Twin" — không mơ hồ.

### Requirements
- [ ] Sau `action_suggestion.complete` event: confirmation + schedule `twin_check_back_in` for next briefing
- [ ] Briefing sáng hôm sau: open với "Hôm qua anh đã đặt mục tiêu [X]. Twin đã cập nhật..."
- [ ] Cadence dial-back: 3+ actions/tuần → reduce tease 50%
- [ ] Phrase rotation: `return_tease.yaml` với 5-7 variants
- [ ] Tease mềm: "Sáng mai check lại nhé 💚" thay vì CTA mạnh

### Files Touched
- `apps/twin_renderer/services/return_tease_service.py` (new)
- `content/twin/return_tease.yaml` (new)
- `apps/briefing/morning_briefing.py` (modify)

### Claude Code Implementation Prompt
```
Implement Story 3.6 of Epic #672 (Phase 4.3):
Return Tease + Loop Closure

PR should close #[ISSUE_NUMBER]
```

