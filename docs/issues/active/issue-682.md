# Issue #682

[Story 3.4] Negative Delta Handling — Phase 4.3

## Story 3.4 — Negative Delta Handling

**Parent Epic:** #672 | **Estimate:** 1 day | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Stories 3.2, 3.5

### User Story
> Là một mass affluent user vừa có tuần xấu, tôi cần Twin nói tin xấu với tôi một cách tôn trọng + có giải pháp — không né tránh, không guilt-inducing.

### Requirements
- [ ] Copy file `negative_delta_copy.yaml` với 5-7 variants cho different scenarios (mild/moderate/significant/severe)
- [ ] Causality breakdown: focus 1 factor largest, KHÔNG chia weight nhỏ lẻ
- [ ] Action suggestion: "Review 3 khoản chi lớn nhất tháng" — concrete, không vague
- [ ] Banned words (auto-check): "lỗi", "sai", "không nên", "đáng tiếc", "tiếc rằng", "rủi ro", "nguy cơ"
- [ ] Required phrases: "Bé Tiền cùng anh xem lại", "Việc nên làm tiếp"
- [ ] Frequency cap: max 1 negative notification/tuần
- [ ] Visual: "🌧️ Tuần Mưa Của Twin" thay vì "📉 Giảm"
- [ ] Operator approval: 5 sample messages reviewed before production

### Files Touched
- `content/twin/negative_delta_copy.yaml` (new)
- `apps/twin_renderer/services/negative_delta_handler.py` (new)
- `apps/twin_renderer/guards/banned_words_check.py` (new)

### Claude Code Implementation Prompt
```
Implement Story 3.4 of Epic #672 (Phase 4.3):
Negative Delta Handling

PR should close #[ISSUE_NUMBER]
```

