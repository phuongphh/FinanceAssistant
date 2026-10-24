# Issue #685

[Story 4.1] Twin Engagement Funnel Section — Phase 4.3

## Story 4.1 — Twin Engagement Funnel Section

**Parent Epic:** #673 | **Estimate:** 0.75 day | **Priority:** P0 | **Surface:** Admin Web | **Depends on:** Story 3.1

### User Story
> Là một operator, tôi cần thấy funnel: bao nhiêu user xem Twin lần đầu → lần 2 → habit (≥3/tuần) → abandon.

### Requirements
- [ ] Section "Twin Engagement" với 4 funnel stages: First view → 2nd view → Habit threshold → Abandonment
- [ ] Funnel chart + conversion % giữa stages
- [ ] Date range: 7d/14d/30d/custom
- [ ] Cohort filter: signup week, user segment
- [ ] Drill-down: click stage → user list (anonymized, exportable)
- [ ] Refresh: 15 phút

### Files Touched
- `admin-dashboard/src/pages/TwinDashboard/EngagementFunnel.tsx` (new)
- `apps/admin_api/routes/twin_metrics.py` (new endpoints)
- `apps/admin_api/queries/twin_engagement_funnel.sql` (new)

### Claude Code Implementation Prompt
```
Implement Story 4.1 of Epic #673 (Phase 4.3):
Twin Engagement Funnel Section

PR should close #[ISSUE_NUMBER]
```

