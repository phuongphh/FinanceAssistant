# Issue #687

[Story 4.3] Twin Comprehension Signals Section — Phase 4.3

## Story 4.3 — Twin Comprehension Signals Section

**Parent Epic:** #673 | **Estimate:** 0.5 day | **Priority:** P1 | **Surface:** Admin Web | **Depends on:** Stories 1.1, 1.2

### User Story
> Là một operator, tôi cần signal user có hiểu Twin không — qua emoji reactions, time-on-Twin, "Vì sao thay đổi" tap rate.

### Requirements
- [ ] Section "Twin Comprehension" với 4 widgets:
  - Emoji reaction breakdown — stacked bar
  - Time-on-Twin median (target: 30-120s first view, < 30s return) — line chart
  - "Vì sao Twin thay đổi" tap rate — KPI
  - Follow-up question rate — KPI
- [ ] Cohort filter
- [ ] Refresh: 15 phút

### Files Touched
- `admin-dashboard/src/pages/TwinDashboard/ComprehensionSignals.tsx` (new)
- `apps/admin_api/routes/twin_metrics.py` (modify)
- `apps/admin_api/queries/twin_comprehension.sql` (new)

### Claude Code Implementation Prompt
```
Implement Story 4.3 of Epic #673 (Phase 4.3):
Twin Comprehension Signals Section

PR should close #[ISSUE_NUMBER]
```

