# Issue #155

[Wealth] Celebrate wealth level transitions + Vietnamese theme labels

## Background

Hiện tại `backend/wealth/ladder.py` đã detect 4 wealth levels và `update_user_level()` đã trả về `new_level` khi user chuyển band, nhưng chưa có gì gửi cho user. Comment ở `ladder.py:82` đã dự trù: *"so callers can decide whether to fire `wealth_level_up` events"*.

`asset_entry.py:774-779` chỉ track analytics event mà không celebrate.

## Goal

Khi user level-up hoặc level-down qua wealth band, gửi tin nhắn Telegram qua daily milestone job (8h sáng, đã chạy sẵn). Reuse hoàn toàn milestone infrastructure từ Phase 2.

## Vietnamese theme labels (NEW)

Bốn levels được đặt tên tiếng Việt theo theme nông nghiệp/giàu sang Việt Nam, hiển thị cho user:

| Enum (giữ nguyên) | Tên đầy đủ | Tên ngắn (theme) |
|---|---|---|
| `starter` | Bắt đầu tích luỹ | Trồng lúa |
| `young_prof` | Có chút tiết kiệm | Kho thóc |
| `mass_affluent` | Của ăn của để | Phú hộ |
| `hnw` | Giàu sang phú quý | Vương giả |

Enum value DB không đổi (tránh migration rủi ro). Label chỉ ở layer presentation.

## Design decisions (đã chốt với owner)

1. **Timing**: 8h sáng hôm sau qua `check_milestones` job — không real-time. Lý do: gentle, không spam, gộp với daily ritual.
2. **Direction**: Cả level-up và level-down đều gửi. Level-down tone động viên, **tuyệt đối không blame**.
3. **Dedup**: 1 lần ever per level transition. Reuse `(user_id, milestone_type)` unique constraint. Nếu user yo-yo qua boundary (29.5tr ↔ 30.5tr), chỉ celebrate lần đầu.
4. **Content**: 3 ý ngắn — congratulation + educational hint + goal-setting (next milestone).

## Acceptance criteria

### Models (`backend/models/user_milestone.py`)
- [ ] Thêm 6 entries vào `MilestoneType`:
  - `WEALTH_LEVEL_UP_YOUNG_PROF` = `"wealth_level_up_young_prof"`
  - `WEALTH_LEVEL_UP_MASS_AFFLUENT` = `"wealth_level_up_mass_affluent"`
  - `WEALTH_LEVEL_UP_HNW` = `"wealth_level_up_hnw"`
  - `WEALTH_LEVEL_DOWN_STARTER` = `"wealth_level_down_starter"`
  - `WEALTH_LEVEL_DOWN_YOUNG_PROF` = `"wealth_level_down_young_prof"`
  - `WEALTH_LEVEL_DOWN_MASS_AFFLUENT` = `"wealth_level_down_mass_affluent"`

(Note: không có `UP_STARTER` vì user khởi tạo ở Starter; không có `DOWN_HNW` vì không có level cao hơn để xuống từ đó)

### Labels (`backend/wealth/ladder.py`)
- [ ] Thêm `LEVEL_LABELS: dict[WealthLevel, dict[str, str]]` với keys `full` + `short`.
- [ ] Helper `format_level(level, style="short" | "full") -> str`.

### Detection (`backend/services/milestone_service.py`)
- [ ] Hàm mới `_check_wealth_level_changes(db, user_id) -> list[UserMilestone]`.
- [ ] So sánh `user.wealth_level` (current) với highest level đã từng đạt (suy ra từ existing UP milestones).
- [ ] `current_idx > highest_ever_idx` → fire UP milestone cho level mới.
- [ ] `current_idx < highest_ever_idx` AND chưa có DOWN milestone tương ứng → fire DOWN milestone.
- [ ] Plug vào `detect_and_record()`.
- [ ] Extra payload: `{"new_level": "young_prof", "next_target_amount": 100_000_000}`.

### Render context (`backend/services/milestone_service.py:_render_context`)
- [ ] Thêm placeholders:
  - `{level_label}` — tên ngắn của level hiện tại (e.g. "Kho thóc")
  - `{level_full}` — tên đầy đủ (e.g. "Có chút tiết kiệm")
  - `{next_target}` — số tiền milestone tiếp theo, format `format_money_full`
  - `{next_level_label}` — tên ngắn level kế

### Content (`content/milestone_messages.yaml`)
- [ ] 3 entries level-up (UP_YOUNG_PROF, UP_MASS_AFFLUENT, UP_HNW), mỗi entry 2 variations.
- [ ] 3 entries level-down (DOWN_STARTER, DOWN_YOUNG_PROF, DOWN_MASS_AFFLUENT), tone động viên, **không blame**.

Format mẫu (UP_YOUNG_PROF):
```
🎉 {name} ơi, chúc mừng bạn lên cấp Kho thóc rồi!
Level này bạn nên bắt đầu đầu tư thêm — stocks, fund mở đều phù hợp.
🎯 Mục tiêu tiếp: {next_target} → Phú hộ
```

Format mẫu (DOWN_STARTER):
```
🌊 {name} ơi, tài sản tạm về cấp Trồng lúa.
Thị trường có lúc lên lúc xuống — quan trọng là bạn vẫn đang theo dõi.
🎯 Mục tiêu phục hồi: {next_target} → Kho thóc
```

### Tests (`backend/tests/test_milestone_wealth_levels.py` — mới)
- [ ] Test up: starter → YP → fire `WEALTH_LEVEL_UP_YOUNG_PROF`.
- [ ] Test down: YP → starter → fire `WEALTH_LEVEL_DOWN_STARTER` (highest_ever vẫn là YP).
- [ ] Test no-change: stay in same level → no milestone.
- [ ] Test yo-yo dedup: starter → YP → starter → YP → chỉ 1 UP_YP milestone, 1 DOWN_STARTER milestone.
- [ ] Test render: placeholders `{level_label}`, `{next_target}` được fill đúng.
- [ ] Test HNW: không có DOWN_HNW (skip nếu current==HNW vì không xuống được, không có level cao hơn).
- [ ] Test fresh user (no `wealth_level`): không crash, return [].

## Out of scope

- Real-time celebration (defer; 8h sáng đủ tốt cho Phase 3A).
- Animation / confetti UI cho Mini App (đã có ở P3A-24 cho starter milestone, không liên quan).
- Update messages khi user chuyển level nhiều lần trong 1 ngày (chỉ fire 1 lần dù qua nhiều band — `_create_if_missing` đã handle).

## References

- `backend/wealth/ladder.py` — level detection
- `backend/services/milestone_service.py` — milestone infrastructure (Phase 2)
- `backend/jobs/check_milestones.py` — daily 8h job
- `content/milestone_messages.yaml` — copy source of truth
- CLAUDE.md §6 (milestone_service.py) — wealth milestone roadmap đã liệt kê

## Branch

`claude/review-wealth-levels-VBBSA`
