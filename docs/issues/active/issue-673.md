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
- **4.1** Twin Engagement Funnel Section (0.75d, P0, depends on 3.1)
- **4.2** Twin Loop Health Section (1d, P0, depends on 3.3, 3.6)
- **4.3** Twin Comprehension Signals Section (0.5d, P1, depends on 1.1, 1.2)
- **4.4** Twin Delta Distribution Section (0.75d, P0, depends on 3.5)

