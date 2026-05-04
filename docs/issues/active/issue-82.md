# Issue #82

[P3A-24] Milestone progress display for Starter level

## Epic
Epic 4 — Visualization & Testing | **Week 4** | Depends: P3A-21, P3A-22

## Description
UI section hiển thị tiến trình tới wealth milestone tiếp theo. Chỉ hiện cho Starter level.

## Acceptance Criteria
- [ ] Section "🎯 Mục tiêu tiếp theo" visible only when `level === 'starter'`
- [x] Progress bar animated: fill % = current_net_worth / target_milestone
- [ ] Text: "X.Xtr / Y.Ytr để đạt [Level Name]"
- [x] CSS transition 0.5s khi bar fills
- [x] Motivational text: "Tiếp tục thêm Xtr nữa!"
- [x] Milestone achieved celebration:
  - Pass threshold → confetti animation (lightweight library)
  - Trigger Phase 2 milestone event `wealth_level_up`
- [x] Confetti library <10KB gzipped

## Estimate
~0.5 day
