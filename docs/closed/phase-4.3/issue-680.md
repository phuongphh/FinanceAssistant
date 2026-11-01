# Issue #680

[Story 3.2] Causality Breakdown with Contribution Weights — Phase 4.3

## Story 3.2 — Causality Breakdown with Contribution Weights

**Parent Epic:** #672 | **Estimate:** 1 day | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Story 3.1

### User Story
> Là một mass affluent user vừa thấy Twin update, tôi muốn biết CHÍNH XÁC điều gì đã đẩy Twin thay đổi — không phải chung chung "thị trường biến động".

### Requirements
- [ ] Service `twin_causality_service.attribute_delta(user_id, period_days=7)` → list (factor, contribution_pct, action_taken_at, factor_type)
- [ ] Algorithm: snapshot P50 t-7 vs t-now, roll-back each factor individually, normalize weights
- [ ] Top 3-5 factors, group remaining as "Khác"
- [ ] Output format with causality card and forward-looking sentence
- [ ] Cache: `causality:{user_id}:{date_iso}`, TTL 24h, latency < 1s
- [ ] Tap "Vì sao Twin thay đổi?" trigger
- [ ] Button "Việc nên làm tiếp →" link sang Story 3.3
- [ ] Delta gần zero: hide breakdown, show "Twin của anh ổn định tuần này"

### Files Touched
- `apps/twin_renderer/services/causality_service.py` (new)
- `content/twin/causality_explainer.yaml` (new)
- `infra/cache/causality_cache.py` (new)

### Claude Code Implementation Prompt
```
Implement Story 3.2 of Epic #672 (Phase 4.3):
Causality Breakdown with Contribution Weights

PR should close #[ISSUE_NUMBER]
```

