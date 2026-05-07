# Issue #242

[Epic] Phase 3.8.5 — Epic 2: User Profile (View)

## Phase 3.8.5 — Epic 2: User Profile (View)

> **Type:** Epic | **Day:** 3 | **Stories:** 3

## Triết Lý "Anti-Form Profile"
Profile là **VIEW-MODE primary** — hệ thống đã biết mọi thứ (assets, transactions, behavior). Profile chỉ surface data đó cho user thấy. Editable fields cực ít: chỉ display name, age range, notification time.

## Wealth Levels VN-Native (locked, do not change)
| Internal | Vietnamese | Icon | Range |
|---------|-----------|------|-------|
| STARTER | Khởi Đầu | 🌱 | 0-30tr |
| YOUNG_PROF | Trẻ Năng Động | 🚀 | 30-200tr |
| MASS_AFFLUENT | Trung Lưu Vững | 💎 | 200tr-1tỷ |
| HNW | Tinh Hoa | 🏆 | 1tỷ+ |

## Success Definition
- ✅ `/menu → 👤 Profile của tôi` → comprehensive profile view
- ✅ Wealth level hiển thị tiếng Việt
- ✅ Progress to next level shown
- ✅ Auto-derived stats từ existing data (no new data entry)

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.8.5-S4: UserProfile model + WealthLevelMapper
- [ ] [Story] P3.8.5-S5: ProfileStatsAggregator
- [ ] [Story] P3.8.5-S6: Profile view + menu integration

## Dependencies
✅ Epic 1 (parallel OK), Phase 3A assets, Phase 3.8 income/goals

## Reference
`docs/current/phase-3.8.5/phase-3.8.5-detailed.md` § Profile
