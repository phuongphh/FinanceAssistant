# Issue #247

[Story] P3.8.5-S4: UserProfile model + WealthLevelMapper

**Parent Epic:** #242 (Epic 2: User Profile View)

## User Story
As a developer building profile view, I need UserProfile model + WealthLevelMapper với 4 VN-native wealth levels, để system có stable foundation cho profile personalization.

## Wealth Levels (LOCKED — không thay đổi tên)
| Internal | Vietnamese | Icon | Range |
|---------|-----------|------|-------|
| STARTER | Khởi Đầu | 🌱 | 0-30tr |
| YOUNG_PROF | Trẻ Năng Động | 🚀 | 30-200tr |
| MASS_AFFLUENT | Trung Lưu Vững | 💎 | 200tr-1tỷ |
| HNW | Tinh Hoa | 🏆 | 1tỷ+ |

## Acceptance Criteria

### Data Model
- [ ] Migration tạo bảng `user_profiles`: user_id (PK+FK), display_name (nullable, max 50), age_range (nullable enum: 20-29, 30-39, 40-49, 50+), briefing_enabled (bool, default true), briefing_time (HH:MM, default 07:00), reminder_enabled (bool, default true), reminder_time (HH:MM, default 09:00), created_at, updated_at

### Wealth Levels YAML
- [ ] File `content/wealth_levels.yaml` với 4 levels
- [ ] Mỗi level: id, name_vn, name_en, icon, net_worth_min, net_worth_max, description

### WealthLevelMapper Service
- [ ] `get_level(net_worth)` → level dict đúng
- [ ] `get_next_level(net_worth)` → next tier
- [ ] `get_progress_to_next(net_worth)` → {at_top, progress_pct, amount_to_next, next_level_name}
- [ ] Boundary: `>= min AND < max` (consistent)

## Test Plan
```python
def test_starter():
    level = WealthLevelMapper().get_level(Decimal("15000000"))
    assert level["name_vn"] == "Khởi Đầu"

def test_boundary_30tr():
    level = WealthLevelMapper().get_level(Decimal("30000000"))
    assert level["name_vn"] == "Trẻ Năng Động"  # ≥30tr = next level

def test_progress_halfway():
    progress = WealthLevelMapper().get_progress_to_next(Decimal("15000000"))
    assert 49 <= progress["progress_pct"] <= 51
```

## Estimate: ~0.5 day
## Depends on: None
## Reference: `docs/current/phase-3.8.5/phase-3.8.5-detailed.md` § 2.1, 2.2
