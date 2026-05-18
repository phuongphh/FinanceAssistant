# Issue #683

[Story 3.5] Delta Threshold for Noticeable Change — Phase 4.3

## Story 3.5 — Delta Threshold for Noticeable Change

**Parent Epic:** #672 | **Estimate:** 0.5 day | **Priority:** P0 | **Surface:** Backend | **Depends on:** Story 3.1

### User Story
> Là một operator, tôi cần config threshold để Twin chỉ notify khi delta đủ noticeable — tránh spam, tránh silent khi user chờ feedback.

### Requirements
- [ ] Table `twin_delta_threshold_config` (Migration 4.3.05): wealth_segment, threshold_pct_positive, threshold_absolute_vnd_positive, threshold_pct_negative, threshold_absolute_vnd_negative
- [ ] Default seed per wealth segment (starter/young_pro/mass_affluent/hnw)
- [ ] Service `twin_threshold_service.is_noticeable(user_segment, delta_pct, delta_absolute_vnd, direction)` → bool
- [ ] Inclusive at threshold: delta == threshold → noticeable
- [ ] Aggregation: multiple sub-threshold deltas in 24h, sum above → aggregate + notify once
- [ ] Operator command `/twin_threshold_tune <segment> <field> <value>` with audit log

### Files Touched
- `apps/twin_renderer/services/threshold_service.py` (new)
- `db/migrations/4.3.05_twin_delta_threshold_config.sql` (new)
- `apps/operator/commands/twin_threshold_tune.py` (new)

### Claude Code Implementation Prompt
```
Implement Story 3.5 of Epic #672 (Phase 4.3):
Delta Threshold for Noticeable Change

PR should close #[ISSUE_NUMBER]
```

