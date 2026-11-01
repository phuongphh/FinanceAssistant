# Issue #171

[Story] P3.6-S11: Prepare and execute hard cutover deploy

**Parent Epic:** #160 (Epic 3: Migration & Quality Assurance)

## User Story
As a product owner, tôi muốn menu revamp ship cleanly với clear user communication so users feel informed — không phải surprised.

## Acceptance Criteria

### Pre-deploy checklist:
- [ ] Old menu code commented (không delete) với date stamp
- [ ] Old callbacks (`menu_old:*`) gracefully redirect to new menu
- [ ] Analytics event `menu_revamp_deployed` configured
- [ ] Rollback plan documented (single git revert + redeploy command)
- [ ] Smoke test script ready: 1 query mỗi category

### Pre-deploy announcement (1 ngày trước):
- [ ] Gửi tới tất cả active users:
  ```
  📢 Bé Tiền sắp được nâng cấp giao diện mới!
  
  Menu sẽ rõ ràng hơn với 5 mảng:
  💎 Tài sản • 💸 Chi tiêu • 💰 Dòng tiền • 🎯 Mục tiêu • 📊 Thị trường
  
  Cập nhật vào ngày mai 7h sáng. Mọi tính năng vẫn còn!
  ```

### Deploy (off-peak, 7 AM):
- [ ] Push code to production
- [ ] Run `setup_bot_commands()` để update bot menu button
- [ ] Run smoke test: /menu → verify main menu loads
- [ ] Test 1 query per category → verify all work

### Post-deploy notification (trong 1 giờ):
- [ ] Gửi tới tất cả users:
  ```
  ✨ Menu mới đã sẵn sàng! Gõ /menu để khám phá.
  Hoặc cứ hỏi tự nhiên như cũ — mình hiểu mà 😊
  ```

### Monitoring 4h post-deploy:
- [ ] Watch error logs
- [ ] Watch /menu invocation rate
- [ ] Rollback trigger: error rate >5% OR critical flow broken

## Estimate: ~1 day
## Depends on: Epic 2 complete
## Reference: `docs/current/phase-3.6-detailed.md` § 2.2
