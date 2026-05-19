# Issue #686

[Story 4.2] Twin Loop Health Section — Phase 4.3

## Story 4.2 — Twin Loop Health Section

**Parent Epic:** #673 | **Estimate:** 1 day | **Priority:** P0 | **Surface:** Admin Web | **Depends on:** Stories 3.3, 3.6

### User Story
> Là một operator, tôi cần đo chính xác loop close rate: bao nhiêu user đi qua trigger → view → action → return trong 7 ngày.

### Requirements
- [ ] Section "Twin Loop Health" với 4 KPIs:
  - Trigger source breakdown (voluntary/briefing tap/action-triggered) — pie chart
  - Action completion rate (suggested → completed in 48h) — line chart
  - Return rate after action — line chart
  - Full loop close rate (trigger → view → action → return in 7d) — KPI card + trend
- [ ] Alert thresholds: loop < 15% 3 days → operator notify; action completion < 20% 7 days → alert
- [ ] Filter: user segment, cohort week
- [ ] Refresh: 15 phút

### Files Touched
- `admin-dashboard/src/pages/TwinDashboard/LoopHealth.tsx` (new)
- `apps/admin_api/routes/twin_metrics.py` (modify)
- `apps/admin_api/queries/twin_loop_health.sql` (new)
- `apps/admin_api/services/twin_alerts.py` (new)

### Claude Code Implementation Prompt
```
Implement Story 4.2 of Epic #673 (Phase 4.3):
Twin Loop Health Section

PR should close #[ISSUE_NUMBER]
```

