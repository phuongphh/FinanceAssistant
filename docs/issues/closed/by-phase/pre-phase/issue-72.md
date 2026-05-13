# Issue #72

[P3A-14] Build briefing inline keyboard (4 action buttons)

## Epic
Epic 2 — Morning Briefing | **Week 2** | Depends: P3A-12

## Description
Inline keyboard gắn vào mỗi morning briefing message. 4 buttons, 2 rows.

## Acceptance Criteria
- [ ] File `app/bot/keyboards/briefing_keyboard.py`
- [ ] Function `briefing_actions_keyboard()` return InlineKeyboardMarkup
- [ ] Row 1: [📊 Xem dashboard] [💬 Kể chuyện]
- [ ] Row 2: [➕ Thêm tài sản] [⚙️ Điều chỉnh giờ]
- [ ] Callback handlers registered:
  - `briefing:dashboard` → send Mini App link
  - `briefing:story` → start storytelling mode (P3A-18)
  - `asset_add:start` → asset type selector → wizard
  - `briefing:settings` → show briefing time setting menu
- [ ] Analytics: track each button click with `briefing_button_clicked` event
- [ ] Integration test: tap each button → correct flow triggered

## Estimate
~0.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 2.3
