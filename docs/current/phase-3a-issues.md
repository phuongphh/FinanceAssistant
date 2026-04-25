# Phase 3A — GitHub Issues

> **Purpose:** 26 issues sẵn sàng copy-paste vào GitHub, tổ chức theo 4 Epics (tương ứng 4 tuần).  
> **Usage:** Copy mỗi block từ `## [P3A-X]...` tới dòng gạch ngang `---` vào GitHub issue body.  
> **Reference:** Mọi issue link về [phase-3a-detailed.md](./phase-3a-detailed.md)

---

## 📊 Overview

| Epic | Tuần | Issues | Goal |
|------|------|--------|------|
| Epic 1: Asset Data Model & Manual Entry | 1 | P3A-1 → P3A-9 | User nhập được 5 loại asset, xem tổng |
| Epic 2: Morning Briefing Infrastructure | 2 | P3A-10 → P3A-15 | Bot gửi briefing 7h sáng, personalized |
| Epic 3: Storytelling Expense | 3 | P3A-16 → P3A-20 | Threshold-based expense tracking |
| Epic 4: Visualization & Testing | 4 | P3A-21 → P3A-26 | Mini App dashboard, user testing |

---

## 🏷️ GitHub Labels Cần Setup

Trước khi tạo issues, setup các labels sau trong GitHub repo:

**Phase labels:**
- `phase-3a` (color: blue)

**Week labels:**
- `week-1`, `week-2`, `week-3`, `week-4`

**Type labels:**
- `backend` (purple)
- `frontend` (orange)
- `database` (red)
- `ai-llm` (green)
- `testing` (yellow)
- `content` (pink)

**Priority labels:**
- `priority-critical` (red)
- `priority-high` (orange)
- `priority-medium` (yellow)

---

# Epic 1: Asset Data Model & Manual Entry

**Tuần 1** | **Goal:** User nhập được 5 loại asset (cash, stock, real_estate, crypto, gold), xem tổng net worth tính đúng.

---

## [P3A-1] Create database migrations for assets, snapshots, income_streams

**Epic:** Epic 1 — Asset Data Model  
**Week:** 1  
**Depends on:** None  
**Blocks:** P3A-2, P3A-3, P3A-4

### Reference
📖 [phase-3a-detailed.md § 1.1 — Database Schema](./phase-3a-detailed.md)

### Description
Setup 4 database migrations để support wealth tracking:
1. `assets` table — store user's assets với JSON metadata
2. `asset_snapshots` table — daily historical values
3. `income_streams` table — salary, dividend, interest (simple)
4. Update `users` table — add wealth-related fields

### Acceptance Criteria
- [ ] Migration `xxx_create_assets.py` applied với đầy đủ columns: id, user_id, asset_type, subtype, name, description, initial_value, current_value, acquired_at, last_valued_at, metadata JSON, is_active, sold_at, sold_value, timestamps
- [ ] Migration `xxx_create_asset_snapshots.py` applied với (id, asset_id, user_id, snapshot_date, value, source) + unique constraint on (asset_id, snapshot_date)
- [ ] Migration `xxx_create_income_streams.py` applied (source_type, amount_monthly, metadata)
- [ ] Migration `xxx_add_user_wealth_fields.py` applied (primary_currency, wealth_level, expense_threshold_micro, expense_threshold_major, briefing_enabled, briefing_time)
- [ ] Indexes tạo đúng (idx_assets_user, idx_assets_type, idx_snapshots_user_date, idx_income_user)
- [ ] `downgrade()` hoạt động (test rollback)

### Technical Notes
- Dùng `sa.Numeric(20, 2)` cho money fields (không dùng Float)
- JSON metadata flexible cho mỗi loại asset
- `on_delete` cascade cho foreign keys

### Estimate
~0.5 day

### Labels
`phase-3a` `week-1` `database` `priority-critical`

---

## [P3A-2] Implement Asset + AssetSnapshot + IncomeStream models

**Epic:** Epic 1  
**Week:** 1  
**Depends on:** P3A-1  
**Blocks:** P3A-3, P3A-4

### Reference
📖 [phase-3a-detailed.md § 1.1 & § 1.2](./phase-3a-detailed.md)

### Description
Tạo SQLAlchemy models matching với migrations. Thêm helper methods và enums.

### Acceptance Criteria
- [ ] File `app/wealth/models/asset.py` — Asset model đầy đủ columns
- [ ] File `app/wealth/models/asset_snapshot.py` — AssetSnapshot model
- [ ] File `app/wealth/models/income_stream.py` — IncomeStream model
- [ ] File `app/wealth/models/asset_types.py` — AssetType enum (CASH, STOCK, REAL_ESTATE, CRYPTO, GOLD, OTHER)
- [ ] File `content/asset_categories.yaml` — đầy đủ 6 loại với icons, labels, subtypes (theo spec)
- [ ] Helper `get_asset_config(asset_type)` load từ YAML
- [ ] Helper `get_subtypes(asset_type)` return subtypes dict
- [ ] Unit tests cho models (create, read, update)

### Technical Notes
- Dùng `relationship()` để link Asset ↔ AssetSnapshot
- Hybrid property cho `gain_loss = current_value - initial_value`

### Estimate
~1 day

### Labels
`phase-3a` `week-1` `backend` `priority-critical`

---

## [P3A-3] Build AssetService (CRUD + soft delete)

**Epic:** Epic 1  
**Week:** 1  
**Depends on:** P3A-1, P3A-2  
**Blocks:** P3A-6, P3A-7, P3A-8

### Reference
📖 [phase-3a-detailed.md § 1.3](./phase-3a-detailed.md)

### Description
Core service để quản lý assets. Auto-create snapshot khi create/update.

### Acceptance Criteria
- [ ] `AssetService.create_asset()` — tạo asset + first snapshot
- [ ] `AssetService.update_current_value()` — update + create/update snapshot today
- [ ] `AssetService.get_user_assets()` — support include_inactive flag
- [ ] `AssetService.get_asset_by_id()` — với user_id check (security)
- [ ] `AssetService.soft_delete()` — mark is_active=False, không xóa data
- [ ] Unit tests cover all methods
- [ ] Edge case: create asset với current_value=None → default initial_value
- [ ] Edge case: multiple updates same day → update snapshot, không duplicate

### Technical Notes
- Async methods (AsyncSession)
- Raise ValueError nếu asset không thuộc user_id
- Transaction safety (flush trước commit)

### Estimate
~1 day

### Labels
`phase-3a` `week-1` `backend` `priority-critical`

---

## [P3A-4] Build NetWorthCalculator

**Epic:** Epic 1  
**Week:** 1  
**Depends on:** P3A-3  
**Blocks:** P3A-11

### Reference
📖 [phase-3a-detailed.md § 1.4](./phase-3a-detailed.md)

### Description
Calculate user's net worth từ active assets. Support current + historical + change comparison.

### Acceptance Criteria
- [ ] `NetWorthBreakdown` dataclass: total, by_type dict, asset_count, largest_asset
- [ ] `NetWorthChange` dataclass: current, previous, change_absolute, change_percentage, period_label
- [ ] `calculate(user_id)` returns current breakdown
- [ ] `calculate_historical(user_id, date)` uses latest snapshot ≤ date
- [ ] `calculate_change(user_id, period)` supports "day" | "week" | "month" | "year"
- [ ] Edge case: User with 0 assets → returns total=0, not crash
- [ ] Edge case: No historical snapshots → previous=0
- [ ] Edge case: User just created account → change=0
- [ ] Unit tests cover all 3 methods + edge cases

### Technical Notes
- **QUAN TRỌNG:** Dùng `Decimal`, không `float`
- Historical query: `DISTINCT ON (asset_id)` cho performance
- Cache result trong request

### Estimate
~1 day

### Labels
`phase-3a` `week-1` `backend` `priority-critical`

---

## [P3A-5] Implement Wealth Level detection (Ladder)

**Epic:** Epic 1  
**Week:** 1  
**Depends on:** P3A-4  
**Blocks:** P3A-11

### Reference
📖 [phase-3a-detailed.md § 1.5](./phase-3a-detailed.md)  
📜 [strategy.md — Ladder of Engagement](./strategy.md)

### Description
Detect user's wealth level để adapt UI. 4 levels: Starter, Young Professional, Mass Affluent, HNW.

### Acceptance Criteria
- [ ] File `app/wealth/ladder.py` với `WealthLevel` enum
- [ ] `detect_level(net_worth)` đúng:
  - 0 - 30tr → STARTER
  - 30tr - 200tr → YOUNG_PROFESSIONAL
  - 200tr - 1 tỷ → MASS_AFFLUENT
  - 1 tỷ+ → HIGH_NET_WORTH
- [ ] `next_milestone(net_worth)` returns (target_amount, target_level)
- [ ] Milestone logic cho HNW: tăng dần theo tỷ
- [ ] Unit tests cover boundary values (29tr, 30tr, 200tr, 1tỷ)
- [ ] Update `user.wealth_level` khi có asset change

### Estimate
~0.5 day

### Labels
`phase-3a` `week-1` `backend`

---

## [P3A-6] Build Asset Entry Wizard: Cash flow

**Epic:** Epic 1  
**Week:** 1  
**Depends on:** P3A-3  
**Blocks:** P3A-9

### Reference
📖 [phase-3a-detailed.md § 1.6 — Cash Wizard](./phase-3a-detailed.md)

### Description
Wizard đơn giản nhất (2 câu hỏi) cho cash asset. **Entry wizard** — phần lớn users bắt đầu với cash.

### Acceptance Criteria
- [ ] Handler `start_cash_wizard()` — show subtype buttons (bank_savings, bank_checking, cash, e_wallet)
- [ ] Handler `handle_cash_subtype()` — save subtype, ask name + amount
- [ ] Handler `handle_cash_text_input()` — parse flexible:
  - "VCB 100 triệu"
  - "Techcom 50tr"
  - "MoMo 2tr"
  - "Tiết kiệm 500 nghìn"
- [ ] Save asset với source="user_input"
- [ ] Show confirmation + net worth update
- [ ] Offer "Thêm tài sản khác" button
- [ ] Validation: reject số âm, zero
- [ ] Error handling: parse fail → ask lại ấm áp

### Technical Notes
- Reuse `parse_transaction_text` từ Phase 3 cũ (amount parsing)
- Context state trong `context.user_data["asset_draft"]`

### Estimate
~1 day

### Labels
`phase-3a` `week-1` `backend` `priority-critical`

---

## [P3A-7] Build Asset Entry Wizard: Stock flow

**Epic:** Epic 1  
**Week:** 1  
**Depends on:** P3A-3  
**Blocks:** P3A-9

### Reference
📖 [phase-3a-detailed.md § 1.6 — Stock Wizard](./phase-3a-detailed.md)

### Description
Wizard 3-4 bước cho stock/fund asset.

### Acceptance Criteria
- [ ] Handler `start_stock_wizard()` — ask ticker
- [ ] Handler `handle_stock_ticker()` — validate, save metadata.ticker
- [ ] Handler `handle_stock_quantity()` — ask quantity, validate integer
- [ ] Handler `handle_stock_price()` — ask avg price
- [ ] Handler `handle_stock_current_price()` — offer "same as avg" hoặc nhập mới
- [ ] Save metadata: `{"ticker": "VNM", "quantity": 100, "avg_price": 45000, "exchange": "HOSE"}`
- [ ] Support subtypes: vn_stock, fund, etf, foreign_stock
- [ ] Edge case: ticker không tồn tại → vẫn cho save (Phase 3B validate)
- [ ] Edge case: "VNM stocks" → normalize về "VNM"

### Technical Notes
- `initial_value = quantity * avg_price`
- `current_value = quantity * current_price`
- Phase 3B sẽ auto-update từ market

### Estimate
~1 day

### Labels
`phase-3a` `week-1` `backend` `priority-high`

---

## [P3A-8] Build Asset Entry Wizard: Real Estate flow

**Epic:** Epic 1  
**Week:** 1  
**Depends on:** P3A-3  
**Blocks:** P3A-9

### Reference
📖 [phase-3a-detailed.md § 1.6](./phase-3a-detailed.md)  
📜 [strategy.md — Case A/B/C](./strategy.md)

### Description
Wizard cho BĐS. Phase 3A cover Case A (nhà ở) và Case C (đất). Case B (cho thuê) ở Phase 4.

### Acceptance Criteria
- [ ] Handler `start_real_estate_wizard()` — ask subtype (house_primary, land)
- [ ] Ask name ("Nhà Mỹ Đình", "Đất Ba Vì")
- [ ] Ask address (optional)
- [ ] Ask initial_value + acquired_at (năm mua)
- [ ] Ask current_value (giá ước tính hiện tại)
- [ ] Metadata: `{"address": "...", "area_sqm": null, "year_built": null}`
- [ ] Warning nếu user mention rental: "Cho thuê sắp có ở Phase 4"
- [ ] Support "2 tỷ", "2.5 tỷ", "2500tr"
- [ ] Note: "Bạn sẽ update giá trị BĐS khi có thay đổi"

### Technical Notes
- BĐS không có auto-update
- Phase 3B có thể suggest từ batdongsan.com

### Estimate
~1 day

### Labels
`phase-3a` `week-1` `backend` `priority-high`

---

## [P3A-9] Integrate "first asset" step into onboarding

**Epic:** Epic 1  
**Week:** 1  
**Depends on:** P3A-6, P3A-7, P3A-8

### Reference
📖 [phase-3a-detailed.md § 1.7](./phase-3a-detailed.md)  
📖 [phase-2-detailed.md § Onboarding](./phase-2-detailed.md)

### Description
Thêm bước "first asset" sau Phase 2's aha_moment. User thêm ít nhất 1 asset trước khi graduate onboarding.

### Acceptance Criteria
- [ ] Onboarding step `step_6_first_asset` sau `step_5_aha_moment`
- [ ] Keyboard 4 options: Cash (simple), Invest, Real Estate, Skip
- [ ] Tap option → route tới wizard tương ứng
- [ ] "Skip" → lưu `onboarding_skipped_asset=True`, nhắc sau 3 ngày
- [ ] Sau complete first asset → congrats + show first net worth
- [ ] Analytics: `first_asset_added`, `first_asset_skipped`
- [ ] Update `user.onboarding_completed_at` chỉ khi có asset (hoặc skip rõ)

### Technical Notes
- Reuse existing wizards, không duplicate
- State machine: add ONBOARDING_STEP_FIRST_ASSET

### Estimate
~0.5 day

### Labels
`phase-3a` `week-1` `backend`

---

# Epic 2: Morning Briefing Infrastructure

**Tuần 2** | **Goal:** Bot gửi morning briefing 7h sáng (adaptive), personalized theo wealth level.

---

## [P3A-10] Create briefing_templates.yaml (4 levels)

**Epic:** Epic 2  
**Week:** 2  
**Depends on:** P3A-5  
**Blocks:** P3A-11

### Reference
📖 [phase-3a-detailed.md § 2.1](./phase-3a-detailed.md)

### Description
Content file với templates cho từng wealth level. **Content work**, quan trọng hơn code.

### Acceptance Criteria
- [ ] File `content/briefing_templates.yaml`
- [ ] 4 level sections: starter, young_prof, mass_affluent, hnw
- [ ] Mỗi level có:
  - `greeting` — 2-3 variations
  - `net_worth_display.template` với placeholders
  - `net_worth_display.no_change` cho case không đổi
- [ ] Starter extra: `progress_context.template`, `educational_tips` (3-5 tips)
- [ ] Young Prof extra: `action_prompts`
- [ ] Mass Affluent extra: `market_intelligence.template` (placeholder)
- [ ] HNW extra: `detailed_breakdown`
- [ ] Common: `spending_reminder`, `storytelling_prompt`
- [ ] Content review với 2 native VN speakers — không sến súa

### Technical Notes
- YAML multiline string
- Placeholders consistent: `{name}`, `{net_worth}`, `{change}`, `{pct}`, `{period}`, `{breakdown_lines}`, `{threshold}`
- Max 2-3 emoji per section

### Estimate
~1 day (content-heavy)

### Labels
`phase-3a` `week-2` `content` `priority-critical`

---

## [P3A-11] Build BriefingFormatter (ladder-aware)

**Epic:** Epic 2  
**Week:** 2  
**Depends on:** P3A-4, P3A-5, P3A-10  
**Blocks:** P3A-12

### Reference
📖 [phase-3a-detailed.md § 2.2](./phase-3a-detailed.md)

### Description
Generate personalized morning briefing dựa trên wealth level + user data.

### Acceptance Criteria
- [ ] Class `BriefingFormatter` với method `generate_for_user(user) -> str`
- [ ] Auto-detect level từ current net worth
- [ ] Render đúng template cho level
- [ ] `_format_net_worth()` — hero section với change emoji (📈/📉)
- [ ] `_format_breakdown()` — asset type breakdown (sort by value desc)
- [ ] `_format_milestone_progress()` cho Starter — next milestone + ETA estimate
- [ ] `_format_cashflow()` cho Mass Affluent — monthly income/expense/net/saving_rate
- [ ] `_format_storytelling_prompt()` — append cuối
- [ ] Handle edge cases:
  - 0 assets → empty state
  - Net worth = 0 → không divide by zero
  - Change pct = 0 → "không đổi"
- [ ] Output length <800 chars (mobile screen)
- [ ] Test với mock users 4 levels

### Estimate
~1.5 day

### Labels
`phase-3a` `week-2` `backend` `priority-critical`

---

## [P3A-12] Implement morning_briefing_job.py (scheduled)

**Epic:** Epic 2  
**Week:** 2  
**Depends on:** P3A-11  
**Blocks:** P3A-14

### Reference
📖 [phase-3a-detailed.md § 2.3](./phase-3a-detailed.md)

### Description
Scheduled job chạy mỗi 15 phút, gửi briefing cho user nào có briefing_time trong cửa sổ 15 phút tới.

### Acceptance Criteria
- [ ] File `app/scheduled/morning_briefing_job.py`
- [ ] Function `run_morning_briefing_job()`
- [ ] Query active users (30 days) với briefing_enabled=True
- [ ] `_is_within_15_min(now, target_time)` logic đúng
- [ ] `_already_sent_today()` tránh gửi trùng
- [ ] Send với inline keyboard
- [ ] Track `morning_briefing_sent`
- [ ] Rate limit: 1 msg/second
- [ ] Error handling: 1 user fail không crash job
- [ ] APScheduler chạy mỗi 15 phút
- [ ] Log success/failure

### Technical Notes
- Timezone: VN (UTC+7)
- Default briefing_time = 07:00

### Estimate
~1 day

### Labels
`phase-3a` `week-2` `backend` `priority-critical`

---

## [P3A-13] Implement daily_snapshot_job.py (23:59)

**Epic:** Epic 2  
**Week:** 2  
**Depends on:** P3A-2

### Reference
📖 [phase-3a-detailed.md § 2.4](./phase-3a-detailed.md)

### Description
Cuối ngày, tạo snapshot cho MỌI active asset. Cần cho historical comparison.

### Acceptance Criteria
- [ ] File `app/scheduled/daily_snapshot_job.py`
- [ ] Function `create_daily_snapshots()` loop qua active assets
- [ ] Skip nếu đã có snapshot hôm nay (user đã update)
- [ ] Source = "auto_daily"
- [ ] APScheduler chạy 23:59 mỗi ngày (VN time)
- [ ] Handle timezone đúng
- [ ] Log: số snapshots created
- [ ] Error handling: 1 asset fail không crash
- [ ] Unit test với mock assets

### Technical Notes
- Batch insert cho performance
- Unique constraint từ migration → handle conflict

### Estimate
~0.5 day

### Labels
`phase-3a` `week-2` `backend`

---

## [P3A-14] Build briefing inline keyboard

**Epic:** Epic 2  
**Week:** 2  
**Depends on:** P3A-12

### Reference
📖 [phase-3a-detailed.md § 2.3](./phase-3a-detailed.md)

### Description
Inline keyboard gắn vào morning briefing. 4 buttons.

### Acceptance Criteria
- [ ] File `app/bot/keyboards/briefing_keyboard.py`
- [ ] Function `briefing_actions_keyboard()` return InlineKeyboardMarkup
- [ ] Row 1: [📊 Xem dashboard] [💬 Kể chuyện]
- [ ] Row 2: [➕ Thêm tài sản] [⚙️ Điều chỉnh giờ]
- [ ] Callback handlers:
  - `briefing:dashboard` → open Mini App
  - `briefing:story` → start storytelling (dep P3A-18)
  - `asset_add:start` → asset wizard
  - `briefing:settings` → settings menu
- [ ] Analytics: track button clicks
- [ ] Integration test: tap button → correct action

### Estimate
~0.5 day

### Labels
`phase-3a` `week-2` `frontend`

---

## [P3A-15] Analytics tracking: briefing events

**Epic:** Epic 2  
**Week:** 2  
**Depends on:** P3A-12, P3A-14

### Description
Track events để measure retention của Morning Briefing.

### Acceptance Criteria
- [ ] Event `morning_briefing_sent` với properties: level, user_id, timestamp
- [ ] Event `morning_briefing_opened` — khi user tap button trong 30 phút
- [ ] Event `briefing_dashboard_clicked`
- [ ] Event `briefing_story_clicked`
- [ ] Analytics endpoint/dashboard xem:
  - Daily open rate
  - Level breakdown (Starter vs Mass Affluent)
  - Average time-to-open

### Technical Notes
- Reuse Event model từ Phase 1/2
- Simple MVP: log ra DB
- Phase 5 sẽ integrate với analytics tool

### Estimate
~0.5 day

### Labels
`phase-3a` `week-2` `backend`

---

# Epic 3: Storytelling Expense

**Tuần 3** | **Goal:** User kể chuyện, AI extract giao dịch >threshold. Threshold adapt theo income.

---

## [P3A-16] Implement threshold_service.py (income-based)

**Epic:** Epic 3  
**Week:** 3  
**Depends on:** P3A-2  
**Blocks:** P3A-17

### Reference
📖 [phase-3a-detailed.md § 3.1](./phase-3a-detailed.md)

### Description
Tính thresholds (micro + major) adapt theo monthly income.

### Acceptance Criteria
- [ ] File `app/wealth/services/threshold_service.py`
- [ ] Function `compute_thresholds(monthly_income) -> (micro, major)`
- [ ] Income ranges đúng:
  - <15tr → (100k, 1tr)
  - 15tr - 30tr → (200k, 2tr)
  - 30tr - 60tr → (300k, 3tr)
  - 60tr+ → (500k, 5tr)
- [ ] Function `update_user_thresholds(user_id)` auto-update khi income thay đổi
- [ ] User settings UI cho override
- [ ] Edge case: income = 0 → default 200k/2tr
- [ ] Unit tests cover boundaries

### Technical Notes
- Thresholds lưu trong `users` table (P3A-1)
- Income = sum(income_streams.amount_monthly) cho active

### Estimate
~0.5 day

### Labels
`phase-3a` `week-3` `backend`

---

## [P3A-17] Write & test storytelling LLM prompt

**Epic:** Epic 3  
**Week:** 3  
**Depends on:** P3A-16  
**Blocks:** P3A-18

### Reference
📖 [phase-3a-detailed.md § 3.2](./phase-3a-detailed.md)

### Description
**Issue quan trọng nhất Epic 3.** LLM prompt quyết định accuracy toàn bộ feature.

### Acceptance Criteria
- [ ] File `app/bot/personality/storytelling_prompt.py` với `STORYTELLING_PROMPT` constant
- [ ] Function `extract_transactions_from_story(story, user_id, threshold) -> dict`
- [ ] Integration với DeepSeek API (primary)
- [ ] Output JSON schema: `transactions[]`, `needs_clarification[]`, `ignored_small[]`
- [ ] **Test suite với 30+ câu chuyện mẫu:**
  - Đơn giản: "Tối qua ăn nhà hàng 800k"
  - Phức tạp: nhiều giao dịch trong 1 câu
  - Có số nghìn: "mua điện thoại 15 triệu"
  - Có chia sẻ: "ăn với bạn 400k chia đôi" → extract 200k
  - Threshold boundary: với threshold=200k, chỉ extract >200k
  - Không có giao dịch: "đi chơi với bạn" → empty
  - Ambiguous: "mua đồ" → needs_clarification
- [ ] Accuracy ≥80% trên test suite
- [ ] Cost per call <$0.01
- [ ] Fallback nếu LLM parse error → ask user

### Technical Notes
- Test iteratively — chạy test suite, tinh chỉnh, lặp
- Log mọi LLM call để debug
- Cache identical stories

### Estimate
~1.5 day

### Labels
`phase-3a` `week-3` `ai-llm` `priority-critical`

---

## [P3A-18] Build storytelling handler (text + voice)

**Epic:** Epic 3  
**Week:** 3  
**Depends on:** P3A-17  
**Blocks:** P3A-19

### Reference
📖 [phase-3a-detailed.md § 3.3](./phase-3a-detailed.md)

### Description
Handler cho storytelling mode. Nhận text/voice, extract, show confirmation.

### Acceptance Criteria
- [ ] Handler `start_storytelling()` — user tap "Kể chuyện" → enter mode
- [ ] Handler `handle_storytelling_input()` — parse text OR voice
- [ ] Voice: download audio, call Whisper, transcribe
- [ ] Show transcript: "🎤 Mình nghe: ..."
- [ ] Call `extract_transactions_from_story()`
- [ ] Build confirmation message với list
- [ ] Store pending in `context.user_data["pending_transactions"]`
- [ ] Exit mode sau confirm hoặc timeout 10 phút
- [ ] Empty: "Mình không thấy giao dịch nào trên threshold"
- [ ] Error: "Có lỗi, thử lại nhé?"

### Technical Notes
- Voice: reuse `transcribe_vietnamese()` từ archive
- Mode state: `context.user_data["storytelling_mode"] = True`

### Estimate
~1 day

### Labels
`phase-3a` `week-3` `backend` `priority-critical`

---

## [P3A-19] Build confirmation UI with inline actions

**Epic:** Epic 3  
**Week:** 3  
**Depends on:** P3A-18

### Reference
📖 [phase-3a-detailed.md § 3.3](./phase-3a-detailed.md)

### Description
UI để user confirm / edit / cancel list giao dịch.

### Acceptance Criteria
- [ ] Inline keyboard: [✅ Đúng hết] [✏️ Sửa] [❌ Bỏ hết]
- [ ] "Đúng hết" → save all với source="storytelling", verified_by_user=True
- [ ] "Bỏ hết" → discard, clear pending
- [ ] "Sửa" → show từng transaction với Edit/Remove/Keep
- [ ] Edit flow: tap Edit → ask sửa gì (amount/merchant/category)
- [ ] Sau confirm: success message với summary
- [ ] Show net worth impact nếu có
- [ ] Clear pending_transactions sau action

### Estimate
~1 day

### Labels
`phase-3a` `week-3` `frontend` `priority-high`

---

## [P3A-20] Integrate storytelling with briefing keyboard

**Epic:** Epic 3  
**Week:** 3  
**Depends on:** P3A-14, P3A-18

### Description
Link button "💬 Kể chuyện" từ briefing vào storytelling flow.

### Acceptance Criteria
- [ ] Button "💬 Kể chuyện" trigger `start_storytelling()`
- [ ] Context đúng: biết user từ briefing (vs direct command)
- [ ] Command `/story` hoặc `/kechuyen` cũng trigger
- [ ] End-to-end test: briefing → tap → kể → confirm → lưu DB
- [ ] Analytics: `storytelling_from_briefing` vs `storytelling_direct`

### Estimate
~0.5 day

### Labels
`phase-3a` `week-3` `backend`

---

# Epic 4: Visualization & Testing

**Tuần 4** | **Goal:** Mini App dashboard đẹp, 7-user testing validated.

---

## [P3A-21] Build Mini App dashboard HTML/CSS

**Epic:** Epic 4  
**Week:** 4  
**Depends on:** Phase 1 Mini App setup  
**Blocks:** P3A-23

### Reference
📖 [phase-3a-detailed.md § 4.1](./phase-3a-detailed.md)

### Description
Màn hình "North Star" — nơi user xem tổng tài sản. Cần đẹp, fast load.

### Acceptance Criteria
- [ ] File `app/miniapp/templates/net_worth_dashboard.html`
- [ ] File `app/miniapp/static/css/wealth.css`
- [ ] Sections:
  1. Hero card: Net worth + change
  2. Pie chart: Asset breakdown
  3. Breakdown list: icon + label + value + %
  4. Trend chart: Line 30/90/365 ngày
  5. Milestone section (starter only)
  6. Assets list với edit
- [ ] Responsive cho mobile (iPhone SE + Pro Max)
- [ ] Loading state với spinner
- [ ] Dark mode support (Telegram theme params)
- [ ] Empty state: "Bắt đầu bằng việc thêm tài sản đầu tiên"
- [ ] `Telegram.WebApp.expand()` để full screen

### Technical Notes
- Vanilla JS (không framework)
- Chart.js từ CDN
- CSS variables cho theming

### Estimate
~1.5 day

### Labels
`phase-3a` `week-4` `frontend` `priority-critical`

---

## [P3A-22] Implement /api/wealth/overview endpoint

**Epic:** Epic 4  
**Week:** 4  
**Depends on:** P3A-4, P3A-5  
**Blocks:** P3A-23

### Reference
📖 [phase-3a-detailed.md § 4.1](./phase-3a-detailed.md)

### Description
API endpoint trả về đầy đủ data cho dashboard.

### Acceptance Criteria
- [ ] Route `GET /miniapp/api/wealth/overview`
- [ ] Auth: `require_miniapp_auth`
- [ ] Response JSON schema đầy đủ (net_worth, level, change_day, change_month, breakdown, trend_90d, assets, next_milestone)
- [ ] Performance: <500ms cho user có 10+ assets
- [ ] Endpoint phụ `GET /api/wealth/trend?days=30|90|365`
- [ ] Error handling: 401 auth fail, 500 graceful

### Technical Notes
- Cache response 30 giây
- Colors map từ `asset_categories.yaml`

### Estimate
~1 day

### Labels
`phase-3a` `week-4` `backend` `priority-critical`

---

## [P3A-23] Chart.js integration: pie + trend charts

**Epic:** Epic 4  
**Week:** 4  
**Depends on:** P3A-21, P3A-22

### Reference
📖 [phase-3a-detailed.md § 4.1](./phase-3a-detailed.md)

### Description
Interactive charts với Chart.js.

### Acceptance Criteria
- [ ] File `app/miniapp/static/js/wealth_dashboard.js`
- [ ] Pie chart (doughnut) cho asset breakdown
- [ ] Line chart cho 90-day trend
- [ ] Tooltips format tiền Việt ("1.5tr" thay vì "1500000")
- [ ] Period selector: 30/90/365 — re-fetch và re-render
- [ ] Smooth animations
- [ ] Colors match asset_categories.yaml
- [ ] Responsive: charts resize theo screen
- [ ] Click pie slice → highlight + tooltip

### Technical Notes
- Load async sau initial render (skeleton)
- Chart.js 4.4.0

### Estimate
~1 day

### Labels
`phase-3a` `week-4` `frontend`

---

## [P3A-24] Milestone display for starter level

**Epic:** Epic 4  
**Week:** 4  
**Depends on:** P3A-21, P3A-22

### Description
UI hiển thị progress tới milestone tiếp theo (chỉ Starter).

### Acceptance Criteria
- [ ] Section "🎯 Mục tiêu tiếp theo" show khi `level === 'starter'`
- [ ] Progress bar fill % = current / target
- [ ] Text: "X.Xtr / Y.Ytr"
- [ ] Animation khi bar fill (transition 0.5s)
- [ ] Milestone achieved celebration:
  - Pass milestone → confetti animation
  - Trigger Phase 2's milestone system
- [ ] Motivation: "Tiếp tục tiết kiệm X triệu nữa để đạt mục tiêu!"

### Technical Notes
- CSS transitions
- Confetti: lightweight library

### Estimate
~0.5 day

### Labels
`phase-3a` `week-4` `frontend`

---

## [P3A-25] User testing protocol with 7 users

**Epic:** Epic 4  
**Week:** 4  
**Depends on:** All previous Phase 3A issues  
**Blocks:** P3A-26

### Reference
📖 [phase-3a-detailed.md § 4.2](./phase-3a-detailed.md)

### Description
Validation experiment quyết định Phase 3A có ship production hay cần iterate.

### Acceptance Criteria
- [ ] Recruit 7 users:
  - 2 Level 0 (Starter): 22-25 tuổi
  - 3 Level 1 (Young Prof): 26-32 tuổi
  - 2 Level 2 (Mass Affluent): 35-45 tuổi
- [ ] Consent form (privacy, right to delete)
- [ ] Day 1: Guided onboarding (30 phút call)
- [ ] Day 2-6: Tự dùng, nhận briefing 7h
- [ ] Daily check-in qua text (1 câu)
- [ ] Day 7: Full interview 30 phút
- [ ] Analytics tracking:
  - briefing_opened (# users/7)
  - dashboard_viewed
  - storytelling_completed
  - asset_added
- [ ] Spreadsheet results
- [ ] Success criteria check:
  - ≥5/7 users mở briefing ≥5/7 ngày
  - ≥4/7 users add asset sau ngày 1
  - ≥3/7 users storytelling ≥3 lần
  - ≥5/7 users sẵn lòng trả ≥100k/tháng
- [ ] Document insights và issues

### Technical Notes
- Setup analytics trước khi test
- Backup DB daily
- Screen recording với consent

### Estimate
~5 days (trọn tuần)

### Labels
`phase-3a` `week-4` `testing` `priority-critical`

---

## [P3A-26] Bug fixes from user testing feedback

**Epic:** Epic 4  
**Week:** 4 (end)  
**Depends on:** P3A-25

### Description
Catch-all cho bugs/improvements phát hiện trong testing.

### Acceptance Criteria
- [ ] Bug list triage (critical / high / medium / low)
- [ ] Critical fix 100%
- [ ] High fix ≥80%
- [ ] Medium/Low: document, defer
- [ ] Regression test
- [ ] Exit review: Phase 3A ready cho public beta?

### Decision Points

**Nếu ≥3/4 success criteria pass:**
- ✅ Ship Phase 3A public beta
- Tiếp tục Phase 3B

**Nếu 2/4 pass:**
- 🔄 Iterate 1 tuần nữa
- Re-test với 3-5 users mới

**Nếu <2/4 pass:**
- 🛑 Reconsider positioning
- Thay đổi lớn cần xem xét

### Estimate
~2 days

### Labels
`phase-3a` `week-4` `priority-high`

---

# 🎯 Epic Dependencies Graph

```
Epic 1 (Week 1) ──────┬──→ Epic 2 (Week 2) ───┐
  P3A-1 → P3A-2       │    P3A-10             │
    → P3A-3 ─┬→ P3A-6 │       ↓               ├──→ Epic 4 (Week 4)
            ├→ P3A-7  │    P3A-11             │    P3A-21, P3A-22
            └→ P3A-8  │       ↓               │       ↓
                 ↓    │    P3A-12             │    P3A-23, P3A-24
              P3A-9   │    P3A-13 (parallel)  │       ↓
                      │    P3A-14, P3A-15     │    P3A-25 (testing)
                      │                       │       ↓
    P3A-4 (Calculator)│                       │    P3A-26 (fixes)
    P3A-5 (Ladder)    │
      └───────────────┘
                      └──→ Epic 3 (Week 3) ──→ Epic 4
                           P3A-16
                              ↓
                           P3A-17 (prompt)
                              ↓
                           P3A-18, P3A-19, P3A-20
```

**Parallel opportunities:**
- Tuần 1: P3A-4, P3A-5 song song với P3A-6/7/8
- Tuần 2: P3A-13 độc lập với P3A-12
- Tuần 3: P3A-17 là blocker chính, start sớm

---

# 📝 Setup GitHub Project

## Step 1: Tạo Project Board
1. GitHub repo → Projects → New Project
2. Template: "Board" (Kanban)
3. Name: "Phase 3A — Wealth Foundation"

## Step 2: Setup Columns
- 📋 **Backlog** — issues chưa bắt đầu
- 🏗️ **In Progress** — đang code
- 👀 **Review** — PR đã mở
- ✅ **Done** — merged

## Step 3: Create Labels
Setup labels ở đầu file này.

## Step 4: Create Issues
Copy từng issue từ file này → paste vào GitHub. Assign labels, milestone, assignee.

## Step 5: Link Dependencies
"Depends on" — use GitHub issue references (#1, #2) sau khi tạo. GitHub auto-link và show graph.

## Step 6: Bắt đầu với P3A-1
First issue. Tất cả khác phụ thuộc vào database foundation.

---

# 💡 Tips Implement Với Claude Code

**1. Share full context:**
```
Đọc:
- docs/current/strategy.md (vision)
- docs/current/phase-3a-detailed.md (WHAT)
- [Issue #P3A-X] cụ thể (focus)
```

**2. One issue at a time:**
Đừng làm nhiều issues cùng lúc. Mỗi issue = 1 PR.

**3. Test-driven:**
Nhờ Claude Code viết tests TRƯỚC. Acceptance criteria là test cases sẵn.

**4. Review carefully:**
AI-generated code cần human review. Focus: security, performance, edge cases.

**5. Document decisions:**
Deviate từ spec → note trong PR description. Update docs nếu permanent.

---

**Good luck với Phase 3A! 🚀**  
**Nhớ:** Ship sớm, validate, iterate. Đừng perfect quá mới release. 💚
