# Issue #172

[Story] P3.6-S12: User testing with 3 users post-deploy

**Parent Epic:** #160 (Epic 3: Migration & Quality Assurance)

## User Story
As a product owner, tôi cần real user feedback trong 48h sau deploy để verify menu mới thực sự tốt hơn menu cũ.

## Acceptance Criteria
- [ ] Recruit 3 real users: 1 Starter, 1 Mass Affluent, 1 HNW
- [ ] Mỗi user explore new menu 10-15 phút
- [ ] **4 tasks cho mỗi user:**
  1. Tìm net worth của bạn
  2. Xem chi tiêu tháng này theo loại
  3. Thêm 1 mục tiêu mới (hoặc check goals nếu không add được)
  4. Check VNM giá hôm nay

- [ ] **Capture per task:** thời gian hoàn thành, confusion points, có dùng free-form không
- [ ] **Post-test interview 15 min:**
  - Menu mới tốt hơn/tệ hơn/như cũ?
  - Intro text có helpful không?
  - Có lúc nào confused không?
  - Prefer menu hay free-form?

### Success Metrics:
- [ ] Tất cả 3 users complete tất cả 4 tasks
- [ ] Average task time <2 phút
- [ ] 0 users nói "menu cũ tốt hơn"
- [ ] ≥2 users notice warmer tone

- [ ] Document findings trong `docs/current/phase-3.6-user-test-results.md`
- [ ] Decision: ship as-is OR iterate?

## Estimate: ~2 days (1 day testing + 1 day analyzing)
## Depends on: P3.6-S11
## Reference: `docs/current/phase-3.6-detailed.md` § 2.3
