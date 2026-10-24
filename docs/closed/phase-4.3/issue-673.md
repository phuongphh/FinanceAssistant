# Issue #673

[Epic 4] Twin Admin Dashboard — Phase 4.3

## 📌 Epic 4: Twin Admin Dashboard

**Phase:** 4.3 | **Estimate:** 3 days | **Priority:** P0 | **Surface:** Admin Web | **Depends on:** Phase 4.2.5 stable

### Goal
Cho operator visibility real-time vào Twin loop health — phát hiện sớm trong soft launch nếu loop fail (low engagement, low action completion, high abandonment).

### Description
Phase 4.2.5 admin dashboard có generic KPI (DAU/MAU/cost). Twin là USP nên xứng đáng dedicated section. 4 sub-section: Engagement Funnel, Loop Health, Comprehension Signals, Delta Distribution. Tất cả extend pattern Phase 4.2.5, không tạo new infra.

### Success Criteria
- [ ] Dashboard ship cùng Twin features (ngày 1 soft launch operator có visibility)
- [ ] Latency dashboard load < 3s với caching
- [ ] Operator có thể identify Twin engagement drop trong 1 ngày

### Stories
| # | Title | Issue | Estimate | Depends |
|---|-------|-------|----------|---------|
| 4.1 | Twin Engagement Funnel Section | [#685](https://github.com/phuongphh/FinanceAssistant/issues/685) | 0.75d | #679 |
| 4.2 | Twin Loop Health Section | [#686](https://github.com/phuongphh/FinanceAssistant/issues/686) | 1d | #681, #684 |
| 4.3 | Twin Comprehension Signals Section | [#687](https://github.com/phuongphh/FinanceAssistant/issues/687) | 0.5d (P1) | #674, #675 |
| 4.4 | Twin Delta Distribution Section | [#688](https://github.com/phuongphh/FinanceAssistant/issues/688) | 0.75d | #683 |

### Claude Code Prompt
```
Implement Epic 4 (Phase 4.3) — all 4 stories (#685–#688).
Branch: phase-4.3/epic-4-twin-admin-dashboard
```

