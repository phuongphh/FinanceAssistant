# Issue #355

[Story] P3.9.5-S17: Audit static emoji + lập mapping

**Parent Epic:** #338 (Epic 5: Telegram Animation Emojis)

## Description
Grep tất cả static emoji trong user-facing strings, tạo mapping → Telegram premium animation emoji ID.

## Acceptance Criteria
- [ ] Grep output list top 20-30 emoji theo frequency
- [ ] File mới content/emoji_animation_map.yaml với schema:
  ```yaml
  money_bag:
    static: 💰
    animation_id: "5368324170671202286"
    contexts: [briefing, milestones]
  ```
- [ ] Map cover: 💰 💎 🎯 📊 📈 📉 💡 🔥 ✅ 🎉 ⚠️ 💸 🏆 📅 💼
- [ ] Document source của animation_id
- [ ] vi-localization-checker pass

## Estimate: ~0.4 day
## Dependencies: None

Close #338
