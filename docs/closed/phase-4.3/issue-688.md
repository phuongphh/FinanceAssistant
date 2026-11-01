# Issue #688

[Story 4.4] Twin Delta Distribution Section — Phase 4.3

## Story 4.4 — Twin Delta Distribution Section

**Parent Epic:** #673 | **Estimate:** 0.75 day | **Priority:** P0 | **Surface:** Admin Web | **Depends on:** Story 3.5

### User Story
> Là một operator, tôi cần thấy phân bố delta hằng tuần per segment để (a) calibrate threshold, (b) phát hiện sớm nếu Twin math sai.

### Requirements
- [ ] Section "Twin Delta Distribution" với 3 widgets:
  - Delta histogram per wealth segment — overlay threshold line
  - P50 estimate distribution per cohort — snapshot wealth trajectory
  - Calibration tracking (predictions vs actuals) — scatter plot
- [ ] Filter: segment, time window
- [ ] Export CSV
- [ ] Refresh: 15 phút
- [ ] Alert: >80% positive cohort-wide → "Twin math possibly biased"

### Files Touched
- `admin-dashboard/src/pages/TwinDashboard/DeltaDistribution.tsx` (new)
- `apps/admin_api/routes/twin_metrics.py` (modify)
- `apps/admin_api/queries/twin_delta_distribution.sql` (new)

### Claude Code Implementation Prompt
```
Implement Story 4.4 of Epic #673 (Phase 4.3):
Twin Delta Distribution Section

PR should close #[ISSUE_NUMBER]
```

