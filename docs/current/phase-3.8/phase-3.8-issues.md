# Phase 3.8 — GitHub Issues (Epics + User Stories)

> **Purpose:** 5 Epics chứa 15 User Stories — 1 epic per major component.  
> **Format:** Epic = 1 component. Stories within = atomic deliverables.  
> **Reference:** [phase-3.8-detailed.md](./phase-3.8-detailed.md)

---

## 📊 Overview

| Epic | Tuần | Stories | Goal |
|------|------|---------|------|
| Epic 1: Rental Property Tracking | 1 | 3 stories | BĐS cho thuê tracking complete |
| Epic 2: Multi-Income Streams | 1 | 3 stories | Multi-source income tracking |
| Epic 3: Recurring + Reminders | 1-2 | 4 stories | Detect + remind for recurring |
| Epic 4: Cashflow Forecasting | 2 | 2 stories | Simple v1 forecast + runway |
| Epic 5: Goals Management | 2 | 3 stories | Templates + projection + CRUD |

**Total:** 15 user stories across 5 epics, ~2 weeks of work.

---

## 🏷️ GitHub Labels

**Phase 3.8 specific:**
- `phase-3.8` (color: green)
- `epic`, `story` (existing)
- `wealth-domain` (specific area)
- `rental`, `income`, `recurring`, `forecast`, `goals` (per-component)

---

# Epic 1: Rental Property Tracking

> **Type:** Epic | **Phase:** 3.8 | **Week:** 1 | **Stories:** 3

## Overview

Build rental property (Case A — chủ nhà cho thuê) tracking. Users can mark existing real_estate assets as rentals, track monthly rent + expenses, see net yield.

## Why This Epic Matters

Mass Affluent target users typically have ≥1 rental property (BĐS cho thuê). Without tracking this, their **net worth shows static value** — missing the active income generation. Phase 3.8 fixes this gap.

## Success Definition

When Epic 1 is complete:
- ✅ User can mark a real_estate asset as rental during creation OR after
- ✅ User can update occupancy status (rented / vacant / self-use)
- ✅ Bot reports show "passive income from rentals" separately
- ✅ Annual yield % calculated automatically
- ✅ Phase 3.7 agent can query rental info ("BĐS nào đang cho thuê?", "thu nhập từ BĐS")

## Stories

- [ ] #XXX [Story] P3.8-S1: Extend Asset model with rental fields
- [ ] #XXX [Story] P3.8-S2: Build RentalService + business logic
- [ ] #XXX [Story] P3.8-S3: Update asset wizard to capture rental data

## Reference

📖 [phase-3.8-detailed.md § 1.1 — Rental Property Tracking](./phase-3.8-detailed.md)

### Labels
`phase-3.8` `epic` `wealth-domain` `rental` `priority-high`

---

## [Story] P3.8-S1: Extend Asset model with rental fields

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~0.5 day | **Depends on:** None

### Reference
📖 [phase-3.8-detailed.md § 1.1](./phase-3.8-detailed.md)

### User Story

As a developer extending wealth tracking, I need to add `is_rental` boolean and `rental_metadata` JSON to the Asset model so that real_estate assets can carry rental-specific data without affecting other asset types.

### Acceptance Criteria

- [ ] Migration adds `is_rental` (Boolean, default False, nullable False) to assets table
- [ ] Migration adds `rental_metadata` (JSON, nullable True) to assets table
- [ ] Pydantic schema `RentalMetadata` defined with:
  - monthly_rent (Decimal)
  - occupancy_status (Literal: "rented" | "vacant" | "self_use")
  - tenant_name (Optional str)
  - lease_start_date / lease_end_date (Optional date)
  - monthly_expenses (Decimal, default 0)
  - deposit_held (Decimal, default 0)
- [ ] Schema computed properties:
  - `net_monthly_yield` (rent - expenses)
  - `annual_yield_pct(property_value)` (annual net / value × 100)
- [ ] All existing tests pass after migration
- [ ] `is_rental` default False ensures existing assets unchanged

### Definition of Done

- Migration ran on dev DB
- All existing assets have `is_rental=False`
- Pydantic models validate sample data correctly

### Labels
`phase-3.8` `story` `backend` `data-model` `priority-critical`

---

## [Story] P3.8-S2: Build RentalService + business logic

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.8-S1

### Reference
📖 [phase-3.8-detailed.md § 1.1 — Service Layer](./phase-3.8-detailed.md)

### User Story

As a system tracking rentals, I need a RentalService that handles mark-as-rental, occupancy updates, and yield aggregation so that rental logic is centralized and reusable across UI + agent.

### Acceptance Criteria

- [ ] File `app/wealth/services/rental_service.py` with class `RentalService`
- [ ] Method `mark_as_rental(asset_id, rental_metadata)`:
  - Validates asset_type == "real_estate"
  - Sets is_rental=True
  - Stores metadata
  - Auto-creates `rental` IncomeStream (will be done as part of Epic 2 wiring)
  - Returns updated asset
- [ ] Method `update_occupancy(asset_id, new_status, effective_date)`:
  - Updates occupancy_status
  - If status changes from "rented" → "vacant", pause linked income stream
  - If reverse, resume income stream
- [ ] Method `unmark_as_rental(asset_id)`:
  - Sets is_rental=False
  - Removes rental_metadata
  - Pauses linked income streams
- [ ] Method `get_rental_yield_summary(user_id)`:
  - Returns aggregated stats: property_count, occupied_count, total_monthly_rent, total_monthly_expenses, net_monthly_yield, annual_passive_income
- [ ] Edge cases tested:
  - Mark non-real_estate as rental → ValueError
  - Update occupancy of non-rental asset → no-op or error
  - Empty user (no rentals) → returns zeros gracefully

### Test Plan

```python
async def test_mark_as_rental():
    asset = await create_real_estate(user, name="Nhà Mỹ Đình", value=2_500_000_000)
    metadata = RentalMetadata(monthly_rent=Decimal("15000000"), occupancy_status="rented", ...)
    
    updated = await RentalService().mark_as_rental(asset.id, metadata)
    assert updated.is_rental == True
    assert updated.rental_metadata["monthly_rent"] == 15000000

async def test_yield_summary():
    user = create_user_with_2_rentals()
    summary = await RentalService().get_rental_yield_summary(user.id)
    assert summary["property_count"] == 2
    assert summary["net_monthly_yield"] > 0
```

### Definition of Done

- All methods implemented + tested
- Test coverage ≥85%
- Service can be called from agent tools

### Labels
`phase-3.8` `story` `backend` `rental` `priority-critical`

---

## [Story] P3.8-S3: Update asset wizard to capture rental data

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.8-S2

### Reference
📖 [phase-3.8-detailed.md § 1.1 — Wizard Integration](./phase-3.8-detailed.md)

### User Story

As a user adding a real_estate asset, I want the bot to ask if it's a rental property and collect rent + expense info so I don't have to do it as a separate step later.

### Acceptance Criteria

- [ ] When user enters real_estate wizard (Phase 3A flow), after basic info, bot asks:
  - "Đây có phải là BĐS cho thuê không?"
  - Buttons: [✅ Có] [❌ Không]
- [ ] If user taps **❌ Không** → wizard ends as before (no changes)
- [ ] If user taps **✅ Có** → enter rental sub-wizard:
  - Q1: "Tiền thuê hàng tháng?" (text input, parse VND)
  - Q2: "Chi phí hàng tháng (thuế, sửa chữa)?" (text, default 0)
  - Q3: "Trạng thái hiện tại?" [Đang cho thuê] [Đang trống]
  - Q4 (only if rented): "Thông tin thêm? (tên người thuê, ngày thuê)" [Skip] [Thêm]
- [ ] On wizard completion:
  - Asset saved with is_rental=True + rental_metadata
  - Bot confirms: "✅ Đã thêm BĐS cho thuê **[Name]** — Nhận **[rent]/tháng** ([yield]% năm)"
- [ ] **Add new menu action** in Phase 3.6 menu under Tài sản:
  - "🏠 Đánh dấu BĐS cho thuê" — for marking existing assets after creation
  - Wizard: list real_estate assets → user picks → enters rental sub-wizard
- [ ] Validation:
  - Monthly rent must be > 0
  - Monthly expenses ≥ 0 (can be 0)
  - If lease dates provided, end_date > start_date

### User Flow Sample

```
[User in real_estate wizard]
Bot: "Đây có phải là BĐS cho thuê không?"
[✅ Có] [❌ Không]
User: ✅ Có
Bot: "💰 Tiền thuê hàng tháng?"
User: "15tr"
Bot: "🛠️ Chi phí hàng tháng (thuế, sửa chữa, môi giới)? Gửi 0 nếu không có."
User: "1.5tr"
Bot: "📍 Trạng thái?"
[🏠 Đang cho thuê] [🚪 Đang trống]
User: 🏠 Đang cho thuê
Bot: "Bạn muốn ghi thêm thông tin gì không?"
[👤 Thêm tên thuê] [📅 Thêm ngày thuê] [✅ Hoàn tất]
User: ✅ Hoàn tất
Bot: "✅ Đã thêm BĐS cho thuê 'Nhà Mỹ Đình':
     • Thuê: 15tr/tháng
     • Chi phí: 1.5tr/tháng
     • Net yield: 13.5tr/tháng (~6.5%/năm)
     
     Mình tự động tạo income stream 'Thu nhập thuê BĐS' nhé."
```

### Definition of Done

- Both flows work (during creation + post-creation)
- Wizard handles edge cases (skip, error, validation)
- Confirmation message includes computed yield
- Test E2E in real Telegram

### Labels
`phase-3.8` `story` `bot-handler` `rental` `priority-high`

---

# Epic 2: Multi-Income Streams

> **Type:** Epic | **Phase:** 3.8 | **Week:** 1 | **Stories:** 3

## Overview

Build multi-income tracking — users can have salary + freelance + dividend + rental + interest + other simultaneously. Each with own schedule.

## Why This Epic Matters

Mass Affluent users rarely have single income source. Bé Tiền's current single salary model under-represents reality → cashflow analysis skewed → Twin predictions wrong.

## Success Definition

When Epic 2 is complete:
- ✅ User can add multiple income streams via wizard
- ✅ 6 income types supported (salary, freelance, dividend, rental, interest, other)
- ✅ Schedule types work (monthly, quarterly, annually, ad_hoc)
- ✅ Total monthly income aggregated correctly
- ✅ Active vs Passive income breakdown shown
- ✅ Phase 3.7 agent can query income data

## Stories

- [ ] #XXX [Story] P3.8-S4: IncomeStream model + service
- [ ] #XXX [Story] P3.8-S5: Income wizard via Telegram menu
- [ ] #XXX [Story] P3.8-S6: Add GetIncome tool to Phase 3.7 agent

## Reference

📖 [phase-3.8-detailed.md § 1.2 — Multi-Income Streams](./phase-3.8-detailed.md)

### Labels
`phase-3.8` `epic` `income` `priority-high`

---

## [Story] P3.8-S4: IncomeStream model + service

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1 day | **Depends on:** None

### Acceptance Criteria

- [ ] Migration creates `income_streams` table per spec
- [ ] Model `IncomeStream` with all fields (see detailed.md § 1.2)
- [ ] Service `IncomeService` with methods:
  - `add_income_stream(user_id, stream_data)`
  - `update_income_stream(stream_id, updates)`
  - `pause_stream(stream_id)` / `resume_stream(stream_id)`
  - `get_active_streams(user_id)`
  - `get_total_monthly_income(user_id)` returns dict with total, active, passive, ratio, count
- [ ] Helper `_normalize_to_monthly(stream)`:
  - monthly → as-is
  - quarterly → /3
  - annually → /12
  - ad_hoc → average over last 6 months actual receipts (TODO if no history: return amount)
- [ ] **Income types loaded from YAML** (`content/income_types.yaml`):
  - 6 types with metadata (label, is_passive, typical_schedule)
- [ ] Test: User has salary 30tr/month + dividend 10tr/year → total monthly = 30tr + (10/12)tr ≈ 30.83tr

### Labels
`phase-3.8` `story` `backend` `income` `priority-high`

---

## [Story] P3.8-S5: Income wizard via Telegram menu

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1 day | **Depends on:** P3.8-S4

### Reference
📖 [phase-3.8-detailed.md § 1.2 — Wizard Integration](./phase-3.8-detailed.md)

### Acceptance Criteria

- [ ] **Update Phase 3.6 menu** action `menu:cashflow:income`:
  - Currently shows "thu nhập của tôi"
  - Now: list current streams + button "➕ Thêm thu nhập mới"
- [ ] Wizard flow when adding new stream:
  - Q1: "Loại thu nhập?" — buttons for 6 types (with emojis)
  - Q2: "Số tiền?" — text input, parse VND
  - Q3: "Bao lâu nhận 1 lần?" [Hàng tháng] [Hàng quý] [Hàng năm] [Bất định]
  - Q4 (if monthly): "Ngày nào trong tháng?" — number 1-31
  - Q4 (if annually): "Tháng nào?" — buttons 1-12
  - Q5: "Ngày bắt đầu?" — date picker or "Hôm nay"
- [ ] **Auto-create rental stream** when rental property marked (link to source_asset_id)
- [ ] List view shows:
  - Each stream with icon, name, amount, schedule
  - Total monthly equivalent
  - Active/passive ratio bar visual
  - Edit/Delete buttons per stream
- [ ] **Empty state** for new users: "Chưa có nguồn thu nào. Thêm cái đầu tiên!"

### Labels
`phase-3.8` `story` `bot-handler` `income`

---

## [Story] P3.8-S6: Add GetIncome tool to Phase 3.7 agent

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~0.5 day | **Depends on:** P3.8-S4

### Acceptance Criteria

- [ ] New file `app/agent/tools/get_income.py`
- [ ] Tool name: `get_income`
- [ ] Description for LLM (5+ examples):
  - "thu nhập của tôi" → all streams
  - "thu nhập thụ động" → filter passive=true
  - "thu nhập chủ động" → filter passive=false
  - "thu nhập từ thuê BĐS" → filter type=rental
  - "lương tháng này của tôi" → filter type=salary
- [ ] Pydantic input schema with: `stream_type` filter, `is_passive` filter
- [ ] Output: list of streams + aggregated stats
- [ ] Registered in ToolRegistry
- [ ] **Test critical query:** "thu nhập thụ động của tôi" → returns rental + dividend + interest only

### Labels
`phase-3.8` `story` `agent` `priority-high`

---

# Epic 3: Recurring + Reminders

> **Type:** Epic | **Phase:** 3.8 | **Week:** 1-2 | **Stories:** 4

## Overview

Build recurring transaction system + reminder scheduler. Auto-detect patterns from history, allow manual additions, send reminders before due dates.

## Why This Epic Matters

User explicitly requested reminders ("tôi muốn có reminder cho các khoản chi tiêu theo hàng tháng như thế này"). Reminders create daily touchpoints = retention. Foundation for cashflow forecasting too.

## Success Definition

- ✅ Bot detects monthly recurring patterns from 6 months history
- ✅ Bot suggests patterns to user with confirm/reject buttons
- ✅ User can manually add recurring (e.g., rent, internet, gym)
- ✅ Reminders sent 2 days before expected date
- ✅ Reminder has buttons: Đã trả / Trễ vài ngày / Tắt nhắc

## Stories

- [ ] #XXX [Story] P3.8-S7: RecurringPattern model + manual entry
- [ ] #XXX [Story] P3.8-S8: Auto-detection job for recurring patterns
- [ ] #XXX [Story] P3.8-S9: Reminder scheduler + Telegram notifications
- [ ] #XXX [Story] P3.8-S10: Reminder action handlers (paid/delay/disable)

## Reference

📖 [phase-3.8-detailed.md § 1.3 — Recurring Transactions + Reminders](./phase-3.8-detailed.md)

### Labels
`phase-3.8` `epic` `recurring` `reminder` `priority-high`

---

## [Story] P3.8-S7: RecurringPattern model + manual entry

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1 day | **Depends on:** None

### Acceptance Criteria

- [ ] Migration creates `recurring_patterns` table per spec
- [ ] Migration extends `transactions` table with `is_recurring` Bool + `recurrence_id` FK
- [ ] Model `RecurringPattern` with all fields
- [ ] Service `RecurringService` with methods:
  - `add_pattern(user_id, name, category, amount, schedule)`
  - `update_pattern(pattern_id, updates)`
  - `disable_pattern(pattern_id)` (soft delete)
  - `get_active_patterns(user_id)`
  - `link_transaction_to_pattern(transaction_id, pattern_id)`
  - `get_next_expected_date(pattern)` — based on last_occurrence + schedule
- [ ] **Manual add via Telegram menu:**
  - Add to Phase 3.6 menu under Chi tiêu: "🔄 Khoản định kỳ"
  - List existing + button "➕ Thêm khoản định kỳ"
  - Wizard: Tên → Số tiền → Loại (food/housing/...) → Hàng tháng vào ngày? → Bật nhắc nhở?
- [ ] **Sample patterns to test:**
  - "Thuê nhà 15tr ngày 5"
  - "Internet 500k ngày 1"
  - "Netflix 260k ngày 15"

### Labels
`phase-3.8` `story` `backend` `recurring` `priority-critical`

---

## [Story] P3.8-S8: Auto-detection job for recurring patterns

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1.5 days | **Depends on:** P3.8-S7

### Reference
📖 [phase-3.8-detailed.md § Auto-Detection Algorithm](./phase-3.8-detailed.md)

### Acceptance Criteria

- [ ] `RecurringDetector` class with:
  - `detect_patterns(user_id)` returns list of suggestions
  - `_group_similar(transactions)` by (category, amount±10%)
  - `_looks_recurring(group)` heuristic: 3+ occurrences, 25-35 day intervals
  - `_compute_typical_day(group)` median day of month
  - `_most_common_merchant(group)` for context
- [ ] Detection runs nightly via cron job (Celery or APScheduler)
- [ ] **Suggestion delivery via Telegram:**
  - Top 3 suggestions per user per detection run
  - Message format:
    ```
    🔍 Mình thấy bạn có vẻ trả khoản này hàng tháng:
    
    💸 Tên: Thuê nhà
    💰 Số tiền: ~15tr
    📅 Thường vào ngày: 5
    🔁 Đã xảy ra: 4 lần trong 4 tháng
    
    Có phải hàng tháng không?
    [✅ Đúng, ghi nhận] [❌ Không, bỏ qua] [✏️ Sửa lại]
    ```
- [ ] **Don't spam:** if user already rejected similar pattern, skip in future detections
- [ ] **Rate limit:** max 3 suggestions per user per week
- [ ] Store detection state in `pattern_suggestions_log` for tracking
- [ ] Test scenarios:
  - User pays 15tr "thuê nhà" 4 months in a row → detected
  - User eats different restaurants 4 times → NOT detected (different merchants OR amounts)

### Labels
`phase-3.8` `story` `backend` `automation` `recurring`

---

## [Story] P3.8-S9: Reminder scheduler + Telegram notifications

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1 day | **Depends on:** P3.8-S7

### Reference
📖 [phase-3.8-detailed.md § Reminder Scheduler](./phase-3.8-detailed.md)

### Acceptance Criteria

- [ ] `ReminderScheduler` class:
  - `run_daily()` — runs at 9 AM via cron
  - Queries patterns where: enable_reminders=True, next_expected_date - today ≤ reminder_days_before, last_reminder_sent != today
  - Sends Telegram message per pattern
- [ ] **Reminder message format:**
  ```
  ⏰ Nhắc nhẹ — [Hôm nay/Ngày mai/X ngày nữa] là tới hạn:
  
  💸 **Thuê nhà**
  📅 Dự kiến: 05/06
  💰 Khoảng 15,000,000đ
  
  Bạn đã trả chưa?
  ```
- [ ] **Inline keyboard:**
  - [✅ Đã trả] callback `reminder:paid:{pattern_id}`
  - [⏭️ Trễ vài ngày] callback `reminder:delay:{pattern_id}`
  - [🔕 Tắt nhắc nhở] callback `reminder:disable:{pattern_id}`
- [ ] **Reminder bundling:** if user has 3+ patterns due same day, send 1 combined message:
  ```
  📋 Hôm nay có 3 khoản đến hạn:
  
  🏠 Thuê nhà — 15,000,000đ
  🌐 Internet — 500,000đ
  🏋️ Gym — 800,000đ
  
  Tổng: 16,300,000đ
  
  [✅ Đã trả tất cả] [📝 Ghi chi tiết] [🔕 Tắt nhắc]
  ```
- [ ] Update `last_reminder_sent` after each send
- [ ] **Don't double-send:** if user already paid (transaction matched pattern this period), skip reminder
- [ ] Logged in audit trail

### Labels
`phase-3.8` `story` `bot-handler` `reminder` `priority-critical`

---

## [Story] P3.8-S10: Reminder action handlers (paid/delay/disable)

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~0.5 day | **Depends on:** P3.8-S9

### Acceptance Criteria

- [ ] Callback handler for `reminder:paid:{pattern_id}`:
  - Show wizard: "Số tiền đã trả?" (default = expected_amount)
  - Wizard: "Có note gì không?" → optional
  - Create Transaction with is_recurring=True, recurrence_id=pattern_id
  - Update pattern.last_occurrence_date = today
  - Confirm: "✅ Đã ghi nhận. Lần sau dự kiến: [next_expected_date]"
- [ ] Callback `reminder:delay:{pattern_id}`:
  - Don't create transaction
  - Snooze reminder: send again in 2 days
  - Reply: "⏭️ Hiểu rồi, mình nhắc lại sau 2 ngày."
- [ ] Callback `reminder:disable:{pattern_id}`:
  - Set pattern.enable_reminders = False
  - Reply: "🔕 OK, mình không nhắc nữa. Mở lại bất cứ lúc nào trong /menu → Chi tiêu → Khoản định kỳ."
- [ ] Test: full reminder lifecycle (sent → paid → next reminder scheduled)

### Labels
`phase-3.8` `story` `bot-handler` `reminder`

---

# Epic 4: Cashflow Forecasting (Simple v1)

> **Type:** Epic | **Phase:** 3.8 | **Week:** 2 | **Stories:** 2

## Overview

Build simple v1 cashflow forecasting using last 3 months averages + known recurring transactions. Foundation for Twin predictions.

## Success Definition

- ✅ User can ask "tháng tới tiết kiệm bao nhiêu?" → forecast shown
- ✅ Runway analyzer warns if liquid assets <3 months expenses
- ✅ Phase 3.7 agent has new `forecast_cashflow` tool
- ✅ Confidence levels shown (decay with distance)

## Stories

- [ ] #XXX [Story] P3.8-S11: CashflowForecaster + RunwayAnalyzer
- [ ] #XXX [Story] P3.8-S12: ForecastCashflow tool integration

## Reference

📖 [phase-3.8-detailed.md § 2.1 — Cashflow Forecasting](./phase-3.8-detailed.md)

### Labels
`phase-3.8` `epic` `forecast` `priority-high`

---

## [Story] P3.8-S11: CashflowForecaster + RunwayAnalyzer

**Type:** Story | **Epic:** Epic 4 | **Estimate:** ~1.5 days | **Depends on:** Epic 2 + Epic 3 done

### Reference
📖 [phase-3.8-detailed.md § 2.1](./phase-3.8-detailed.md)

### Acceptance Criteria

- [ ] `CashflowForecaster` class:
  - `forecast(user_id, months_ahead=3)` returns list of `MonthlyForecast`
  - Each forecast: month, expected_income, expected_expense, expected_savings, confidence, breakdown, notes
  - **Methodology:**
    - Baseline: average last 3 months income + expense
    - Add: known recurring (high confidence)
    - Add: scheduled income (salary day, dividend dates)
    - Confidence decay: month 1=85%, month 2=70%, month 3=55%
- [ ] `RunwayAnalyzer` class:
  - `compute_runway(user_id)` returns dict with months, liquid_assets, monthly_burn, warning
  - **Liquid assets** = cash + savings (not stocks/BĐS — illiquid)
  - **Essential expenses** = recurring patterns + base average (excluding lifestyle)
  - Warnings: <3 months ("🚨"), 3-6 months ("⚠️"), >6 months (no warning)
- [ ] Edge cases:
  - User has <3 months data → use available, mark low confidence
  - User has 0 income tracked → forecast based on expenses only, warn
  - User has 0 expenses tracked → forecast just income
- [ ] Test scenarios:
  - User stable monthly: forecast matches reality ±10%
  - User with rental income: forecast includes 15tr each month
  - User with quarterly dividend: forecast spikes correct months

### Labels
`phase-3.8` `story` `backend` `forecast` `priority-critical`

---

## [Story] P3.8-S12: ForecastCashflow tool integration

**Type:** Story | **Epic:** Epic 4 | **Estimate:** ~0.5 day | **Depends on:** P3.8-S11

### Acceptance Criteria

- [ ] File `app/agent/tools/forecast_cashflow.py`
- [ ] Tool description for LLM with examples:
  - "tháng tới tôi tiết kiệm bao nhiêu?" → forecast 1 month
  - "dự đoán cashflow 3 tháng tới" → forecast 3 months
  - "bao giờ tôi âm tài khoản?" → runway analysis
- [ ] Input schema: `months_ahead` (1-12), `include_runway` (bool)
- [ ] Output: forecast list + optional runway info
- [ ] Registered in ToolRegistry
- [ ] **Response formatter:**
  - Show monthly breakdown with emoji (📈 income, 📉 expense, 💎 savings)
  - Show confidence level
  - If runway warning, prominent display
- [ ] **Critical test query:** "Tháng 7 dự kiến tôi tiết kiệm bao nhiêu?" → specific number with confidence

### Labels
`phase-3.8` `story` `agent` `priority-high`

---

# Epic 5: Goals Management

> **Type:** Epic | **Phase:** 3.8 | **Week:** 2 | **Stories:** 3

## Overview

Replace Phase 3.6 goal stubs with full CRUD using templates + projection service. 7 templates covering most user goal types.

## Success Definition

- ✅ User picks from 7 templates OR creates custom goal
- ✅ Goal projection shows months_remaining, required_monthly_savings, feasibility
- ✅ Phase 3.6 menu actions all functional (no more stubs)
- ✅ Phase 3.7 agent can query goals

## Stories

- [ ] #XXX [Story] P3.8-S13: Goal model + templates YAML
- [ ] #XXX [Story] P3.8-S14: GoalProjectionService + feasibility analysis
- [ ] #XXX [Story] P3.8-S15: Goal wizard + CRUD via Telegram

## Reference

📖 [phase-3.8-detailed.md § 2.2 — Goals Management Complete](./phase-3.8-detailed.md)

### Labels
`phase-3.8` `epic` `goals` `priority-high`

---

## [Story] P3.8-S13: Goal model + templates YAML

**Type:** Story | **Epic:** Epic 5 | **Estimate:** ~0.5 day | **Depends on:** None

### Acceptance Criteria

- [ ] Migration creates `goals` table per spec (or extends existing if Phase 3A had stub)
- [ ] Model `Goal` with fields: name, icon, target_amount, target_date, current_amount, monthly_savings_required, status, priority, linked_assets
- [ ] **YAML templates** at `content/goal_templates.yaml` with 7 entries:
  - 🚗 Mua xe (200tr - 1.5 tỷ, 12-60 months)
  - 🏠 Mua nhà (1.5 tỷ - 10 tỷ, 36-120 months)
  - ✈️ Du lịch (10tr - 200tr, 3-24 months)
  - 🌅 Hưu trí (3 tỷ - 20 tỷ, 120-360 months)
  - 🎓 Học vấn (50tr - 1 tỷ, 12-60 months)
  - 💒 Đám cưới (200tr - 1 tỷ, 6-24 months)
  - 🛡️ Quỹ khẩn cấp (50tr - 500tr, 6-24 months)
- [ ] Each template has: id, name, category, icon, typical_amount_range, typical_timeline_months, suggested_questions
- [ ] Service method `get_templates()` returns list

### Labels
`phase-3.8` `story` `backend` `data-model` `goals`

---

## [Story] P3.8-S14: GoalProjectionService + feasibility analysis

**Type:** Story | **Epic:** Epic 5 | **Estimate:** ~1 day | **Depends on:** P3.8-S13, Epic 4

### Reference
📖 [phase-3.8-detailed.md § 2.2 — Projection Service](./phase-3.8-detailed.md)

### Acceptance Criteria

- [ ] `GoalProjectionService` class:
  - `project_goal(goal_id)` returns dict with all projection data
  - **If target_date set:** computes required_monthly_savings + feasibility
  - **If no target_date:** computes estimated_completion_months/date based on actual saving rate
- [ ] Feasibility levels:
  - `easy`: required ≤ 0.5 × actual saving (have 2x+ buffer)
  - `feasible`: 0.5-1.0 × (current saving sufficient)
  - `stretch`: 1.0-1.5 × (need to save 1.5x current)
  - `ambitious`: 1.5-2.0 ×
  - `needs_revision`: >2.0 × (unrealistic)
- [ ] Helper `_get_avg_monthly_savings(user_id)`:
  - Returns avg savings last 3 months
  - Uses CashflowForecaster baseline
- [ ] **Supportive framing:** never use harsh language, always offer alternatives
- [ ] Test scenarios:
  - User saves 8tr/month, goal "Mua xe 800tr in 2 years" → required 33tr, feasibility=needs_revision
  - User saves 8tr/month, goal "Mua xe 800tr in 8 years" → required 8.3tr, feasibility=feasible

### Labels
`phase-3.8` `story` `backend` `goals` `priority-high`

---

## [Story] P3.8-S15: Goal wizard + CRUD via Telegram

**Type:** Story | **Epic:** Epic 5 | **Estimate:** ~1.5 days | **Depends on:** P3.8-S14

### Reference
📖 [phase-3.8-detailed.md § 2.2 — Goal CRUD via Telegram](./phase-3.8-detailed.md)

### Acceptance Criteria

- [ ] **Update Phase 3.6 menu** Mục tiêu sub-menu actions:
  - `menu:goals:list` — list active goals with progress bars
  - `menu:goals:add` — start template wizard
  - `menu:goals:update` — update progress on existing
  - `menu:goals:advisor` — projection + feasibility (uses agent)
- [ ] **Add wizard flow:**
  - Q1: Show 7 template buttons + "✏️ Tự tạo"
  - Q2: "Số tiền mục tiêu?" — text, parse VND
  - Q3: "Khi nào muốn đạt được?" [6 tháng] [1 năm] [2 năm] [3 năm] [5 năm] [Tự nhập] [Bỏ qua]
  - Q4 (after Q3): Show projection summary + feasibility
  - Q5: "Save mục tiêu này?" [✅ Có] [📝 Sửa lại]
- [ ] **List view:**
  - Each goal: icon + name + progress bar (▓▓▓░░ 60%)
  - Tap goal → detail view with actions [Update progress] [Edit] [Delete]
- [ ] **Update progress:**
  - "Số tiền mới đã có?" — text
  - Confirms: "✅ Đã update. Còn cần Xtr để hoàn thành. Dự kiến đạt: [date]"
- [ ] **Edit goal:** allow change name, target, date
- [ ] **Delete goal:** confirm dialog
- [ ] **Empty state:** "Chưa có mục tiêu nào! Mục tiêu đầu tiên của bạn là gì?"
- [ ] Test E2E: create from template → update progress → see projection update

### Labels
`phase-3.8` `story` `bot-handler` `goals` `priority-critical`

---

# 🎯 Epic Dependencies Graph

```
Epic 1 (Rental) — independent
Epic 2 (Income) — independent (but rental in Epic 1 auto-creates rental income stream)
Epic 3 (Recurring) — independent

[All 3 above can run parallel in Tuần 1]

Epic 4 (Forecast) — depends on Epic 2 + Epic 3
Epic 5 (Goals) — depends on Epic 4

[Run sequential in Tuần 2]
```

---

# 💡 Implementation Tips

## Reuse Phase 3.7 Tool Pattern

All new agent tools (get_income, forecast_cashflow, get_goals) follow Phase 3.7 pattern:
- Pydantic schemas
- Description with 5+ examples
- Wraps existing service
- Registered in ToolRegistry

## Migration Strategy

5 components = 5 migrations. Run in order:
1. Asset (add rental fields)
2. IncomeStream (new table)
3. RecurringPattern (new table) + Transaction (extend with is_recurring)
4. (Cashflow has no schema)
5. Goal (new or extend)

## Testing Strategy

Phase 3.8 = lots of new data flows. Test fixtures should cover:
- User with rental property (Epic 1)
- User with multiple income streams (Epic 2)
- User with detected + manual recurring (Epic 3)
- User with various forecasts (Epic 4)
- User with goals across all 7 templates (Epic 5)

Reuse 4 personas from Phase 3.7 — extend their data.

## Common Pitfalls

1. **Rental income double-counting** — auto-link manual transactions to recurring pattern
2. **Recurring detection too aggressive** — strict heuristic (3+ occurrences, 25-35 day intervals)
3. **Reminder spam** — bundle if multiple due same day
4. **Forecast over-claimed** — show confidence levels, not single numbers
5. **Goal feasibility too harsh** — supportive framing, always offer alternatives

---

**Phase 3.8 = foundation completion. After this, Twin (Phase 4) can build on solid ground. 💚🏗️**
