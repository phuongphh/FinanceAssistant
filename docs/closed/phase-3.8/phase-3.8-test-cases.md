# Phase 3.8 — Manual Test Cases (Telegram Bot)

<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->

> **Purpose:** Comprehensive test cases for Phase 3.8 (Wealth Completion).  
> **Tester Profile:** No source code access. Tests via Telegram chat + Mini App.  
> **Reference:** [phase-3.8-detailed.md](./phase-3.8-detailed.md), [phase-3.8-issues.md](./phase-3.8-issues.md)

---

## 📋 How to Use This Document

### Test Case Structure

```
TC-XXX: [Title]
Type: Happy | Corner | Regression | Integration | Performance | Critical
Story: P3.8-Sn (links to issue)
Persona: Which test user to use
Preconditions: State required before test
Steps: Numbered actions tester performs
Expected Results: Observable outcomes (in Telegram)
Pass Criteria: All expected results met
```

### Pass / Fail Criteria

- ✅ **PASS:** All Expected Results observed
- ⚠️ **PASS WITH NOTES:** Main behavior correct, minor issues
- ❌ **FAIL:** Any Expected Result not observed
- 🚫 **BLOCKED:** Cannot execute due to dependency

---

## 🧑‍💼 Test Data Setup

**Reuse 4 personas from Phase 3.7, extend with Phase 3.8 data:**

### Persona 1: Hà (Young Professional, 140tr)
**Phase 3.8 specific data:**
- Lương cứng: 25tr/tháng (income stream)
- Freelance: 5-10tr ad-hoc (income stream, irregular)
- Recurring expenses:
  - Thuê nhà: 8tr/tháng (ngày 5)
  - Internet: 300k/tháng (ngày 1)
  - Netflix: 220k/tháng (ngày 15)
- 4 stocks (mixed gains, from Phase 3.7)
- 1 goal: Mua xe 800tr trong 2 năm (Phase 3.6 stub → migrate to full goal)

### Persona 2: Phương (Mass Affluent, 4.5 tỷ)
**Phase 3.8 specific data:**
- Lương: 50tr/tháng
- BĐS Mỹ Đình 2.5 tỷ → **mark as rental**, thuê 15tr/tháng, expenses 1.5tr
- Cổ tức ACB: 30tr/năm (annually, tháng 4)
- Lãi tiết kiệm: 5tr/tháng từ 1 tỷ tiết kiệm
- Recurring expenses:
  - Trường con: 12tr/tháng (ngày 5)
  - Bảo hiểm: 3tr/tháng (ngày 10)
  - Gym + spa: 2tr/tháng (ngày 25)
- 2 goals: Mua nhà 5 tỷ trong 5 năm + Quỹ khẩn cấp 300tr

### Persona 3: Anh Tùng (HNW, 13 tỷ)
**Phase 3.8 specific data:**
- Lương C-level: 150tr/tháng
- 3 BĐS — 2 cho thuê (rental income tổng 60tr/tháng), 1 đang trống
- Cổ tức: 200tr/năm
- Crypto staking: 5tr/tháng
- Recurring: nhiều loại (driver, helper, premium subscriptions)
- 3 goals: Hưu trí 20 tỷ, Mua nhà phố 8 tỷ, Du lịch 500tr

### Persona 4: Minh (Starter, 17tr)
- Lương: 12tr/tháng (single income)
- No rental properties, no goals yet
- For testing empty/edge cases

---

## 🔧 Environment Requirements

- **Bot version:** Phase 3.8 deployed
- **Telegram client:** Mobile (iOS + Android) + Desktop
- **Database:** 4 personas pre-populated với test data
- **Pre-deploy verify:** Phase 3.5/3.6/3.7 still work (regression suite)
- **Cron jobs running:**
  - RecurringDetector (nightly)
  - ReminderScheduler (daily 9 AM)

---

## 📊 Test Coverage Overview

| Section | Test Cases | Type Distribution |
|---------|-----------|-------------------|
| Section 1: Rental Property Tracking | 10 | Happy + Critical |
| Section 2: Multi-Income Streams | 10 | Happy + Integration |
| Section 3: Recurring Auto-Detection | 8 | Happy + Corner |
| Section 4: Recurring Manual + Reminders | 12 | Happy + Critical |
| Section 5: Cashflow Forecasting | 8 | Happy + Integration |
| Section 6: Runway Analysis | 5 | Happy + Corner |
| Section 7: Goals Templates + Wizard | 10 | Happy + Integration |
| Section 8: Goals Projection + Feasibility | 7 | Happy + Compliance |
| Section 9: Agent Integration (3.7 tools) | 6 | Integration |
| Section 10: Regression | 4 | Regression |
| **Total** | **~80** | |

---

# Section 1 — Rental Property Tracking

## TC-001: Mark existing real_estate as rental

**Type:** Happy | **Story:** P3.8-S2 + P3.8-S3 | **Persona:** Phương

**Preconditions:**
- Phương has existing BĐS asset "Nhà Mỹ Đình" worth 2.5 tỷ (NOT yet marked as rental)

**Steps:**
1. Open Telegram chat with Bé Tiền
2. Send `/menu` → 💎 Tài sản → Look for "🏠 Đánh dấu BĐS cho thuê" action
3. Tap that action
4. Bot lists Phương's BĐS assets → tap "Nhà Mỹ Đình"
5. Bot enters rental wizard:
   - Q: "💰 Tiền thuê hàng tháng?" → reply "15tr"
   - Q: "🛠️ Chi phí hàng tháng (thuế, sửa chữa)?" → reply "1.5tr"
   - Q: "📍 Trạng thái?" → tap "🏠 Đang cho thuê"
   - Q: "Bạn muốn ghi thêm thông tin gì?" → tap "✅ Hoàn tất"
6. Wait for confirmation

**Expected Results:**
- Bot confirms: "✅ Đã đánh dấu 'Nhà Mỹ Đình' là BĐS cho thuê"
- Shows summary:
  - Thuê: 15,000,000đ/tháng
  - Chi phí: 1,500,000đ/tháng
  - Net yield: 13,500,000đ/tháng (~6.5%/năm of 2.5 tỷ)
- Bot mentions: "Mình tự động tạo income stream 'Thu nhập thuê BĐS Mỹ Đình' nhé"

**Pass Criteria:**
- Asset marked is_rental=True
- Rental metadata stored correctly
- Yield calculation correct (13.5tr/month, 6.5%/year)
- Auto-creates rental IncomeStream
- No errors

---

## TC-002: Mark rental during initial asset creation

**Type:** Happy | **Story:** P3.8-S3 | **Persona:** Anh Tùng

**Steps:**
1. Send `/add_asset` (or via menu)
2. Choose "🏠 Bất động sản"
3. Enter property: "Căn hộ Quận 7", giá 3 tỷ
4. After basic info, bot asks: "Đây có phải là BĐS cho thuê không?"
5. Tap [✅ Có]
6. Complete rental sub-wizard with:
   - Tiền thuê: 20tr
   - Chi phí: 2tr
   - Trạng thái: Đang cho thuê
   - Tên người thuê: Nguyễn A
   - Ngày thuê: 01/01/2026

**Expected Results:**
- Asset created with is_rental=True từ đầu
- Rental metadata complete with tenant info
- Income stream auto-created
- Confirmation shows: yield 7.2%/năm

**Pass Criteria:**
- Wizard handles "Có" path correctly
- All metadata captured
- Single transaction creation flow

---

## TC-003: Skip rental marking — answer No

**Type:** Happy | **Story:** P3.8-S3 | **Persona:** Anh Tùng

**Steps:**
1. Send `/add_asset` → Bất động sản
2. Enter "Nhà cho gia đình ở", giá 4 tỷ
3. Bot asks: "Đây có phải là BĐS cho thuê không?"
4. Tap [❌ Không]

**Expected Results:**
- Wizard ends as before (no rental sub-wizard)
- Asset created with is_rental=False
- No income stream created
- No mention of rental in confirmation

**Pass Criteria:**
- "Không" path works smoothly
- Asset clean (no rental data)

---

## TC-004: Update occupancy — rented to vacant

**Type:** Happy | **Story:** P3.8-S2 | **Persona:** Anh Tùng

**Preconditions:** Anh Tùng has 1 rental property "Nhà Q7" currently rented (TC-002 setup)

**Steps:**
1. Send: `BĐS Q7 không còn cho thuê nữa`
2. Bot detects intent (or use menu: Tài sản → BĐS → Q7 → Update occupancy)
3. Tap "🚪 Đang trống"
4. Confirm

**Expected Results:**
- Bot updates occupancy_status to "vacant"
- Pauses linked rental income stream
- Confirms: "✅ Đã cập nhật 'Nhà Q7' — Đang trống. Tạm dừng tracking thu nhập."
- Future income forecasts skip this rental

**Pass Criteria:**
- Status updated correctly
- Income stream paused (verify via menu Cashflow → Thu nhập)
- No double-counting in next forecast

---

## TC-005: Rental yield summary — multi-property

**Type:** Happy | **Story:** P3.8-S2 | **Persona:** Anh Tùng

**Preconditions:** Anh Tùng has 3 BĐS: 2 cho thuê (1 rented + 1 vacant), 1 ở

**Steps:**
1. Send: `Tổng thu nhập từ BĐS cho thuê của tôi?`

**Expected Results:**
- Bot shows summary:
  - Tổng số BĐS cho thuê: 2
  - Đang cho thuê: 1 (the rented one)
  - Đang trống: 1
  - Net monthly yield: only from rented = 13.5tr (not 18tr if vacant included)
  - Annual passive income: 162tr
- Vacant property mentioned but not contributing to active income

**Pass Criteria:**
- Aggregation correct
- Distinguishes rented vs vacant
- Only rented contributes to yield

---

## TC-006: Phase 3.7 agent — query rentals

**Type:** Integration | **Story:** P3.8-S2 + agent | **Persona:** Phương

**Steps:**
1. Send: `BĐS nào của tôi đang cho thuê?`

**Expected Results:**
- Phase 3.7 agent routes to Tier 2
- Calls get_assets with filter (asset_type=real_estate, is_rental=true, occupancy=rented)
- Returns: "Nhà Mỹ Đình — đang cho thuê 15tr/tháng"

**Pass Criteria:**
- Agent uses correct filter
- Result accurate

---

## TC-007: Edit rental metadata

**Type:** Happy | **Story:** P3.8-S2 | **Persona:** Phương

**Preconditions:** Phương has Nhà Mỹ Đình rental, thuê 15tr

**Steps:**
1. Through menu: Tài sản → Sửa tài sản → Nhà Mỹ Đình → Update rental
2. Change tiền thuê: 15tr → 17tr (rent increase after lease renewal)

**Expected Results:**
- Rental metadata updated
- Linked income stream amount updated
- Future forecasts use new amount
- Confirmation: "✅ Cập nhật. Income stream cũng đã update."

**Pass Criteria:**
- Edit reflects everywhere
- No orphan data

---

## TC-008: Annual yield calculation correctness

**Type:** Happy | **Story:** P3.8-S1 | **Persona:** Phương

**Steps:**
1. View Nhà Mỹ Đình details (2.5 tỷ value, 15tr rent, 1.5tr expenses)

**Expected Results:**
- Annual yield calculation:
  - Net monthly = 15 - 1.5 = 13.5tr
  - Annual net = 13.5 × 12 = 162tr
  - Yield % = 162/2500 × 100 = **6.48%**
- Display rounds to 6.5% or shows precise

**Pass Criteria:**
- Math correct
- Decimal precision (no float errors)

---

## TC-009: Empty state — user has no real_estate

**Type:** Corner | **Story:** P3.8-S2 | **Persona:** Minh

**Steps:**
1. From Minh, navigate menu → Tài sản → "🏠 Đánh dấu BĐS cho thuê"

**Expected Results:**
- Bot replies: "Bạn chưa có BĐS nào. Thêm BĐS trước nhé!"
- Suggests: [➕ Thêm BĐS mới]

**Pass Criteria:**
- Empty state graceful
- Helpful suggestion

---

## TC-010: Mark non-real_estate as rental — error

**Type:** Negative | **Story:** P3.8-S2 | **Persona:** Hà

**Note:** Test internally — UI shouldn't allow this. Verify validation.

**Steps:**
1. (If accessible) Try to call mark_as_rental on a stock asset
2. Or via API directly

**Expected Results:**
- ValueError: "Only real_estate assets can be marked as rental"
- No data corruption

**Pass Criteria:**
- Validation enforced
- Clean error

---

# Section 2 — Multi-Income Streams

## TC-011: Add salary income stream

**Type:** Happy | **Story:** P3.8-S5 | **Persona:** Hà

**Steps:**
1. Send `/menu` → 💰 Dòng tiền → 💼 Thu nhập
2. Tap "➕ Thêm thu nhập mới"
3. Wizard:
   - Loại: tap "💼 Lương"
   - Số tiền: "25tr"
   - Tần suất: tap "Hàng tháng"
   - Ngày trong tháng: "5"
   - Ngày bắt đầu: tap "Hôm nay"
4. Confirm

**Expected Results:**
- Income stream created with type=salary, amount=25M, schedule=monthly day 5
- Bot confirms: "✅ Đã thêm 'Lương' — 25tr/tháng vào ngày 5. Active income."
- Shows in income list

**Pass Criteria:**
- Stream saved correctly
- All fields captured
- Listed under Thu nhập

---

## TC-012: Add multiple income streams

**Type:** Happy | **Story:** P3.8-S5 | **Persona:** Phương

**Steps:**
1. Add salary 50tr/month (similar to TC-011)
2. Add freelance income: type=Freelance, schedule=Bất định, ban đầu 5-10tr/tháng
3. Add cổ tức ACB: type=Cổ tức, 30tr/năm, schedule=Hàng năm tháng 4
4. View income list

**Expected Results:**
- 3 streams visible
- Total monthly equivalent calculated:
  - Salary: 50tr/tháng
  - Cổ tức: 30/12 = 2.5tr/tháng equivalent
  - Freelance: ad_hoc — average needed
  - Total: ~52.5tr + freelance avg
- Active vs Passive breakdown shown:
  - Active (salary, freelance): 50tr + freelance
  - Passive (dividend): 2.5tr
  - Passive ratio displayed (e.g., "5% income là thụ động")

**Pass Criteria:**
- Multiple streams handled
- Schedule normalization correct
- Active/passive classification accurate

---

## TC-013: Income type icons + labels

**Type:** Visual | **Story:** P3.8-S5 | **Persona:** Hà

**Steps:**
1. Open income wizard, see income type buttons

**Expected Results:**
- 6 buttons with emojis:
  - 💼 Lương
  - 💻 Freelance / Công việc thêm
  - 💵 Cổ tức
  - 🏠 Thuê BĐS
  - 🏦 Lãi tiết kiệm
  - 📦 Khác

**Pass Criteria:**
- All 6 types visible
- Icons match
- Vietnamese labels correct

---

## TC-014: Auto-rental income stream

**Type:** Integration | **Story:** P3.8-S2 + P3.8-S5 | **Persona:** Phương

**Preconditions:** Phương completed TC-001 (marked Nhà Mỹ Đình as rental)

**Steps:**
1. Open Thu nhập list

**Expected Results:**
- Auto-created stream visible:
  - Tên: "Thu nhập thuê BĐS Mỹ Đình"
  - Loại: 🏠 Thuê BĐS
  - Số tiền: 15tr/tháng
  - Schedule: Monthly
  - source_asset_id linked to Nhà Mỹ Đình
  - Marked is_passive=true

**Pass Criteria:**
- Auto-link working
- Cannot create duplicate manually
- Updates with rental metadata changes

---

## TC-015: Total monthly income aggregation

**Type:** Happy | **Story:** P3.8-S4 | **Persona:** Phương

**Steps:**
1. After setting up: salary 50tr + rental 15tr (auto) + dividend 30tr/year + interest 5tr/month
2. Send: `Tổng thu nhập của tôi`

**Expected Results:**
- Bot returns total:
  - Total monthly: 50 + 15 + (30/12) + 5 = 72.5tr
  - Active: 50tr (68.9%)
  - Passive: 22.5tr (31.1%)
- Format readable with breakdown

**Pass Criteria:**
- Math correct (account for annual → monthly)
- Active/passive split clear
- Each stream listed

---

## TC-016: Edit income stream

**Type:** Happy | **Story:** P3.8-S5 | **Persona:** Hà

**Steps:**
1. Open income list
2. Tap "Lương" stream → "✏️ Sửa"
3. Change amount: 25tr → 28tr (after raise)

**Expected Results:**
- Stream updated
- Future forecasts use new amount
- Confirmation: "✅ Cập nhật lương: 25tr → 28tr"

**Pass Criteria:**
- Edit working
- Cascading updates (forecast, etc.)

---

## TC-017: Delete income stream

**Type:** Happy | **Story:** P3.8-S5 | **Persona:** Hà

**Steps:**
1. Open income list
2. Tap freelance stream → "🗑️ Xóa"
3. Confirm dialog: [✅ Xóa] [❌ Hủy]

**Expected Results:**
- Stream removed
- Historical data preserved (transactions still exist)
- Future forecasts exclude this stream

**Pass Criteria:**
- Delete cleanly
- Confirmation prompt prevents accident

---

## TC-018: Income query via Phase 3.7 agent

**Type:** Integration | **Story:** P3.8-S6 | **Persona:** Phương

**Steps:**
1. Send: `Thu nhập thụ động của tôi?`

**Expected Results:**
- Agent calls get_income with is_passive=true filter
- Returns:
  - Cổ tức ACB: 2.5tr/tháng equivalent
  - Lãi tiết kiệm: 5tr/tháng
  - Thuê BĐS Mỹ Đình: 15tr/tháng
  - Total passive: 22.5tr/tháng

**Pass Criteria:**
- Filter applied correctly
- Only passive streams shown

---

## TC-019: Active income query

**Type:** Integration | **Story:** P3.8-S6 | **Persona:** Phương

**Steps:**
1. Send: `Thu nhập chủ động của tôi?`

**Expected Results:**
- Agent filters is_passive=false
- Returns: Lương 50tr (only active stream)
- Total active: 50tr/tháng

**Pass Criteria:**
- Filter correct
- Only active shown

---

## TC-020: Empty state — user has no income

**Type:** Corner | **Story:** P3.8-S5 | **Persona:** New test "NoIncome"

**Steps:**
1. Login as new user with no income streams
2. Open menu → Cashflow → Thu nhập

**Expected Results:**
- Empty state: "Chưa có nguồn thu nào. Thêm cái đầu tiên!"
- CTA button [➕ Thêm thu nhập]

**Pass Criteria:**
- Empty state friendly
- Clear path forward

---

# Section 3 — Recurring Auto-Detection

## TC-021: Auto-detect rent payment pattern

**Type:** Happy | **Story:** P3.8-S8 | **Persona:** Hà

**Preconditions:**
- Hà has 4+ months transaction history
- "Thuê nhà" 8tr appears each month around day 5
- Detection job hasn't run yet

**Steps:**
1. Trigger detection job (admin command or wait for nightly run)
2. Wait for suggestion to arrive in Telegram

**Expected Results:**
- Bot sends suggestion message:
  ```
  🔍 Mình thấy bạn có vẻ trả khoản này hàng tháng:
  
  💸 Tên: Thuê nhà
  💰 Số tiền: ~8tr
  📅 Thường vào ngày: 5
  🔁 Đã xảy ra: 4 lần trong 4 tháng
  
  Có phải hàng tháng không?
  [✅ Đúng, ghi nhận] [❌ Không, bỏ qua] [✏️ Sửa lại]
  ```

**Pass Criteria:**
- Suggestion sent (not silent)
- Format matches spec
- Buttons functional

---

## TC-022: Confirm auto-detected pattern

**Type:** Happy | **Story:** P3.8-S8 | **Persona:** Hà

**Preconditions:** Continue TC-021 (suggestion received)

**Steps:**
1. Tap [✅ Đúng, ghi nhận]

**Expected Results:**
- RecurringPattern created with:
  - name="Thuê nhà"
  - amount=8tr
  - day=5
  - auto_detected=True
  - user_confirmed=True
  - enable_reminders=True (default)
- Bot confirms: "✅ Đã ghi nhận. Mình sẽ nhắc bạn 2 ngày trước khi đến hạn."

**Pass Criteria:**
- Pattern saved
- Confirmation clear
- Reminder setup automatic

---

## TC-023: Reject auto-detected pattern

**Type:** Happy | **Story:** P3.8-S8 | **Persona:** Hà

**Steps:**
1. Receive another suggestion (e.g., for "Ăn trưa 50k")
2. Tap [❌ Không, bỏ qua]

**Expected Results:**
- Pattern NOT created
- Bot acknowledges: "OK, mình không track khoản này. Bỏ qua tương tự sau này."
- Suggestion logged as rejected → won't suggest similar again

**Pass Criteria:**
- Rejection respected
- No spam re-suggestions

---

## TC-024: Edit auto-detected before confirming

**Type:** Happy | **Story:** P3.8-S8 | **Persona:** Hà

**Steps:**
1. Receive suggestion
2. Tap [✏️ Sửa lại]
3. Wizard: change name, day, or amount
4. Save

**Expected Results:**
- Pattern saved with user's edits
- Marked auto_detected=True + user_confirmed=True (still detected, but customized)

**Pass Criteria:**
- Edit before confirm working
- Saves customized version

---

## TC-025: Don't detect non-recurring patterns

**Type:** Corner | **Story:** P3.8-S8 | **Persona:** Hà

**Preconditions:** Hà has 4 different restaurant transactions (different amounts, different days)

**Steps:**
1. Wait for detection job

**Expected Results:**
- NO suggestion for restaurant transactions
- Detection correctly identifies non-recurring (different amounts/dates)

**Pass Criteria:**
- False positives avoided
- Only true patterns suggested

---

## TC-026: Detect with amount variance tolerance

**Type:** Corner | **Story:** P3.8-S8 | **Persona:** Phương

**Preconditions:** Phương pays internet bill: 295k, 305k, 320k, 298k (slight variance)

**Steps:**
1. Wait for detection

**Expected Results:**
- Pattern detected (within ±10% tolerance)
- Suggested amount: average ~305k
- Variance noted: "Số tiền thường dao động 295-320k"

**Pass Criteria:**
- Tolerance applied correctly
- Doesn't fail on minor variations

---

## TC-027: Detection rate limit (max 3/week)

**Type:** Corner | **Story:** P3.8-S8 | **Persona:** Anh Tùng (many recurring)

**Preconditions:** Anh Tùng has 10+ undetected patterns

**Steps:**
1. Trigger detection job
2. Count suggestions sent

**Expected Results:**
- Maximum 3 suggestions sent in this run
- Other patterns queued for future weeks
- Bot doesn't spam user

**Pass Criteria:**
- Rate limit enforced (≤3 per detection run)
- Graceful queueing

---

## TC-028: Don't re-suggest rejected patterns

**Type:** Corner | **Story:** P3.8-S8 | **Persona:** Hà

**Preconditions:** Hà rejected "Ăn trưa 50k" pattern in TC-023

**Steps:**
1. Continue eating lunch 50k for 2 more months
2. Wait for next detection job

**Expected Results:**
- Bot does NOT re-suggest same pattern
- Memory of rejection preserved
- Other valid patterns still suggested

**Pass Criteria:**
- Rejection persistence
- No annoying re-suggestions

---

# Section 4 — Recurring Manual + Reminders

## TC-029: Add recurring expense manually

**Type:** Happy | **Story:** P3.8-S7 | **Persona:** Hà

**Steps:**
1. Send `/menu` → 💸 Chi tiêu → "🔄 Khoản định kỳ"
2. Tap "➕ Thêm khoản định kỳ"
3. Wizard:
   - Tên: "Internet"
   - Số tiền: "300k"
   - Loại: tap "🌐 Tiện ích"
   - Ngày trong tháng: "1"
   - Bật nhắc nhở: tap "✅ Có"
4. Confirm

**Expected Results:**
- RecurringPattern created
- Bot confirms: "✅ Đã thêm 'Internet' — 300k vào ngày 1 hàng tháng. Sẽ nhắc bạn 28/X."

**Pass Criteria:**
- Manual entry works
- Reminder enabled by default

---

## TC-030: Receive reminder 2 days before due

**Type:** 🚨 Critical | **Story:** P3.8-S9 | **Persona:** Hà

**Preconditions:**
- Today is 3rd of month
- Hà has "Thuê nhà 8tr" pattern, expected day 5
- Reminder scheduler runs at 9 AM

**Steps:**
1. Wait for 9 AM
2. Check Telegram

**Expected Results:**
- Reminder message arrives:
  ```
  ⏰ Nhắc nhẹ — 2 ngày nữa là tới hạn:
  
  💸 **Thuê nhà**
  📅 Dự kiến: 05/[Month]
  💰 Khoảng 8,000,000đ
  
  Bạn đã trả chưa?
  ```
- 3 buttons:
  - [✅ Đã trả]
  - [⏭️ Trễ vài ngày]
  - [🔕 Tắt nhắc nhở]

**Pass Criteria:**
- Reminder timing correct
- Format matches spec
- Buttons present

---

## TC-031: Tap "Đã trả" — record transaction

**Type:** Critical | **Story:** P3.8-S10 | **Persona:** Hà

**Preconditions:** Reminder received (TC-030)

**Steps:**
1. Tap [✅ Đã trả]
2. Wizard: "Số tiền đã trả?" (default = 8,000,000)
3. Reply: "8tr" (confirm default) or different amount
4. "Note?" → tap [Bỏ qua]

**Expected Results:**
- Transaction created:
  - is_recurring=True
  - recurrence_id=pattern.id
  - amount=8tr
  - category=housing
- Pattern updated:
  - last_occurrence_date = today
  - occurrence_count += 1
- Bot confirms: "✅ Đã ghi nhận. Lần sau dự kiến: 05/[Next Month]"

**Pass Criteria:**
- Transaction linked to pattern
- Pattern stats updated
- Next reminder calculated correctly

---

## TC-032: Tap "Trễ vài ngày" — snooze

**Type:** Happy | **Story:** P3.8-S10 | **Persona:** Hà

**Steps:**
1. From reminder, tap [⏭️ Trễ vài ngày]

**Expected Results:**
- No transaction created
- Reminder rescheduled: send again in 2 days
- Bot replies: "⏭️ Hiểu rồi, mình nhắc lại sau 2 ngày."

**Pass Criteria:**
- Snooze working
- Re-reminder scheduled

---

## TC-033: Tap "Tắt nhắc nhở" — disable

**Type:** Happy | **Story:** P3.8-S10 | **Persona:** Hà

**Steps:**
1. From reminder, tap [🔕 Tắt nhắc nhở]

**Expected Results:**
- pattern.enable_reminders = False
- Pattern still exists (just no more reminders)
- Bot replies: "🔕 OK, mình không nhắc nữa. Mở lại bất cứ lúc nào trong /menu → Chi tiêu → Khoản định kỳ."

**Pass Criteria:**
- Reminder disabled
- Pattern preserved
- Re-enable instructions clear

---

## TC-034: Bundled reminder for multiple patterns same day

**Type:** Critical | **Story:** P3.8-S9 | **Persona:** Phương

**Preconditions:**
- Phương has 3 patterns due today: Trường con 12tr, Bảo hiểm 3tr, Internet 500k
- Reminder scheduler runs

**Steps:**
1. Wait for 9 AM
2. Check Telegram

**Expected Results:**
- ONE bundled message (not 3 separate):
  ```
  📋 Hôm nay có 3 khoản đến hạn:
  
  🎓 Trường con — 12,000,000đ
  🛡️ Bảo hiểm — 3,000,000đ
  🌐 Internet — 500,000đ
  
  Tổng: 15,500,000đ
  
  [✅ Đã trả tất cả] [📝 Ghi chi tiết] [🔕 Tắt nhắc]
  ```

**Pass Criteria:**
- Bundled NOT 3 separate
- Total computed
- Buttons appropriate

---

## TC-035: Bundled "Đã trả tất cả" creates 3 transactions

**Type:** Happy | **Story:** P3.8-S10 | **Persona:** Phương

**Steps:**
1. From bundled reminder (TC-034), tap [✅ Đã trả tất cả]

**Expected Results:**
- 3 transactions created (one per pattern)
- All with expected amounts (12tr, 3tr, 500k)
- All linked to respective patterns
- Bot confirms: "✅ Đã ghi nhận 3 khoản. Tổng 15,500,000đ tháng này."

**Pass Criteria:**
- Multiple transactions created
- Each correctly linked
- No duplicates

---

## TC-036: Don't double-remind if already paid

**Type:** Critical | **Story:** P3.8-S9 | **Persona:** Hà

**Preconditions:**
- Hà has "Thuê nhà" pattern, due day 5
- Today is day 3, reminder sent
- Hà recorded transaction "Thuê nhà 8tr" on day 4 (early payment, manually)

**Steps:**
1. Day 5: Wait for any potential re-reminder

**Expected Results:**
- NO new reminder sent (pattern already has occurrence this period)
- Smart detection: matched manual transaction to pattern

**Pass Criteria:**
- No duplicate reminders
- Manual + auto-tracked harmonized

---

## TC-037: List existing recurring patterns

**Type:** Happy | **Story:** P3.8-S7 | **Persona:** Phương

**Steps:**
1. Menu → Chi tiêu → Khoản định kỳ

**Expected Results:**
- List shows all patterns:
  - 🏠 Thuê nhà — 8tr ngày 5 ✅ Reminders ON
  - 🌐 Internet — 300k ngày 1 ✅
  - 🎬 Netflix — 220k ngày 15 🔕 Reminders OFF
  - 🎓 Trường con — 12tr ngày 5 ✅
- Each has Edit/Delete buttons

**Pass Criteria:**
- All patterns listed
- Status (reminders on/off) clear
- Actions available

---

## TC-038: Edit recurring pattern

**Type:** Happy | **Story:** P3.8-S7 | **Persona:** Hà

**Steps:**
1. From list, tap "Thuê nhà" → "✏️ Sửa"
2. Change amount: 8tr → 9tr (rent increased)
3. Save

**Expected Results:**
- Pattern updated
- Future reminders use 9tr
- Past transactions unchanged

**Pass Criteria:**
- Edit applies forward
- History preserved

---

## TC-039: Delete recurring pattern

**Type:** Happy | **Story:** P3.8-S7 | **Persona:** Hà

**Steps:**
1. From list, tap pattern → "🗑️ Xóa"
2. Confirm

**Expected Results:**
- Pattern soft-deleted (marked inactive)
- No more reminders
- Past transactions remain (with recurrence_id pointing to deleted pattern, but data intact)

**Pass Criteria:**
- Soft delete preserves history
- Reminders stop

---

## TC-040: Reminder time customization

**Type:** Happy | **Story:** P3.8-S7 | **Persona:** Hà

**Steps:**
1. Add new pattern via wizard
2. After "Bật nhắc nhở: Có", bot asks: "Nhắc trước bao nhiêu ngày?" [1] [2] [3] [5] [Tự nhập]
3. Choose 3 days

**Expected Results:**
- Pattern saved with reminder_days_before=3
- Reminder sent 3 days before due date

**Pass Criteria:**
- Customization working
- Reminder timing matches user choice

---

# Section 5 — Cashflow Forecasting

## TC-041: Forecast next month savings

**Type:** Happy | **Story:** P3.8-S11 + P3.8-S12 | **Persona:** Hà

**Preconditions:** 
- Hà has 3+ months of stable income (25tr) and expenses (~17tr)
- Some recurring patterns set up

**Steps:**
1. Send: `Tháng tới tôi tiết kiệm bao nhiêu?`

**Expected Results:**
- Bot returns forecast:
  ```
  📊 Dự đoán tháng [Next Month]:
  
  📈 Thu nhập dự kiến: 25,000,000đ
  📉 Chi tiêu dự kiến: ~17,000,000đ
  💎 Tiết kiệm: ~8,000,000đ
  
  Mức tin cậy: 85%
  ```
- Numbers based on average + recurring patterns
- Confidence level shown

**Pass Criteria:**
- Forecast reasonable (within historical pattern)
- Confidence visible
- Format clear

---

## TC-042: Forecast 3 months ahead

**Type:** Happy | **Story:** P3.8-S11 | **Persona:** Phương

**Steps:**
1. Send: `Dự đoán cashflow 3 tháng tới`

**Expected Results:**
- Bot shows 3-month forecast table:
  - Tháng [n+1]: Income X, Expense Y, Savings Z (confidence 85%)
  - Tháng [n+2]: ... (confidence 70%)
  - Tháng [n+3]: ... (confidence 55%)
- Confidence DECREASES with distance
- Total 3-month projected savings

**Pass Criteria:**
- 3 months shown
- Confidence decay visible
- Numbers accurate

---

## TC-043: Forecast includes scheduled income

**Type:** Critical | **Story:** P3.8-S11 | **Persona:** Phương

**Preconditions:** Phương has dividend ACB 30tr/year, scheduled tháng 4

**Steps:**
1. If now is March, send: `Tháng tới tiết kiệm bao nhiêu?`

**Expected Results:**
- Forecast for April includes the 30tr dividend
- Notes: "Tháng 4 dự kiến cao do nhận cổ tức 30tr"
- Distinct from regular monthly average

**Pass Criteria:**
- Annual schedules captured in correct month
- One-time spikes noted

---

## TC-044: Forecast includes recurring expenses

**Type:** Critical | **Story:** P3.8-S11 | **Persona:** Phương

**Preconditions:** Phương has recurring patterns: Trường con 12tr, Bảo hiểm 3tr, Gym 2tr

**Steps:**
1. Send: `Tháng tới chi bao nhiêu?`

**Expected Results:**
- Expense forecast = recurring (17tr) + variable average
- Total expense reasonable
- Breakdown available

**Pass Criteria:**
- Recurring counted
- No double-counting

---

## TC-045: Confidence level decay correct

**Type:** Integration | **Story:** P3.8-S11 | **Persona:** Hà

**Steps:**
1. Send: `Forecast 6 tháng tới`

**Expected Results:**
- 6 months shown
- Confidence: 85%, 70%, 55%, 40%, 30%, 30% (caps at 30% min)
- Bot may add disclaimer: "Càng xa, càng khó dự đoán chính xác"

**Pass Criteria:**
- Decay matches spec
- Floor at 30%

---

## TC-046: Forecast empty user

**Type:** Corner | **Story:** P3.8-S11 | **Persona:** Minh

**Preconditions:** Minh has minimal data (maybe 1 month)

**Steps:**
1. Send: `Tháng tới tiết kiệm bao nhiêu?`

**Expected Results:**
- Bot adapts: "Mình chưa có đủ data để forecast chắc chắn (chỉ 1 tháng), nhưng dựa trên pattern hiện tại..."
- Returns rough estimate with low confidence (<50%)
- Suggests: "Track thêm vài tháng để forecast chính xác hơn"

**Pass Criteria:**
- Graceful with limited data
- Honest about uncertainty
- Helpful suggestion

---

## TC-047: Pattern-based forecast (mention v2)

**Type:** Integration | **Story:** P3.8-S11 | **Persona:** Phương

**Note:** Phase 3.8 uses simple v1. v2 (pattern detection) comes in Phase 4B. But test that simple v1 produces reasonable results.

**Steps:**
1. Phương has clear monthly pattern + dividend month 4
2. Forecast February → August

**Expected Results:**
- Most months: ~stable savings
- April: spike (dividend included)
- Other months: baseline
- v1 captures known recurring + scheduled

**Pass Criteria:**
- v1 logic produces useful forecasts
- Recurring + scheduled correctly applied

---

## TC-048: Forecast tool description quality

**Type:** Integration | **Story:** P3.8-S12 | **Persona:** Hà

**Steps:**
1. Send variants:
   - "Sắp tới tiết kiệm thế nào?"
   - "Tháng 6 dự kiến chi bao nhiêu?"
   - "Forecast 2 tháng nữa"

**Expected Results:**
- All variants routed to forecast_cashflow tool
- LLM correctly extracts months_ahead from each query
- Reasonable results for each

**Pass Criteria:**
- LLM tool selection accurate (≥90%)
- Different phrasings handled

---

# Section 6 — Runway Analysis

## TC-049: Runway query — healthy state

**Type:** Happy | **Story:** P3.8-S11 | **Persona:** Phương

**Preconditions:** Phương has 600tr cash + 1 tỷ savings = 1.6 tỷ liquid; monthly burn ~30tr

**Steps:**
1. Send: `Nếu mất việc, tôi sống được bao lâu?`

**Expected Results:**
- Bot computes runway:
  - Liquid assets: 1,600,000,000đ
  - Monthly essential expense: ~30,000,000đ
  - Runway: 53 months (~4.4 years)
  - Status: "Runway rất tốt!" (no warning)
- Encouraging tone

**Pass Criteria:**
- Math correct
- No false alarm

---

## TC-050: Runway warning — under 6 months

**Type:** Happy | **Story:** P3.8-S11 | **Persona:** Hà

**Preconditions:** Hà has 50tr cash; monthly burn ~17tr

**Steps:**
1. Send: `Runway của tôi?`

**Expected Results:**
- Runway: ~3 months
- Warning shown: "⚠️ Runway 3-6 tháng — okay nhưng có thể tốt hơn"
- Suggests: "Tăng emergency fund lên 100tr (6 tháng) là an toàn hơn"

**Pass Criteria:**
- Warning level correct (yellow)
- Constructive suggestion

---

## TC-051: Runway critical warning

**Type:** Happy | **Story:** P3.8-S11 | **Persona:** Test "LowCash" (15tr cash, 12tr burn)

**Steps:**
1. Send: `Tôi sống được bao lâu nếu thất nghiệp?`

**Expected Results:**
- Runway: ~1.25 months
- 🚨 Critical warning: "Runway dưới 3 tháng — nên build emergency fund ngay!"
- Suggests action

**Pass Criteria:**
- Critical warning shown
- Tone urgent but not panicky

---

## TC-052: Runway with no liquid assets

**Type:** Corner | **Story:** P3.8-S11 | **Persona:** Test user "AllStocks" (only stocks, no cash)

**Steps:**
1. Send: `Runway của tôi?`

**Expected Results:**
- Bot detects 0 liquid assets
- Returns: "Bạn không có tài sản thanh khoản (cash/savings). Cổ phiếu có thể bán nhưng cần thời gian + có rủi ro thị trường."
- Suggests building cash buffer

**Pass Criteria:**
- Edge case handled
- Helpful explanation

---

## TC-053: Runway calculation explanation

**Type:** Happy | **Story:** P3.8-S11 | **Persona:** Phương

**Steps:**
1. After getting runway result, send: `Tại sao tính như vậy?`

**Expected Results:**
- Bot (Tier 3) explains methodology:
  - "Runway = Tài sản thanh khoản / Chi tiêu cố định hàng tháng"
  - "Tài sản thanh khoản: cash + tiết kiệm (không tính BĐS, cổ phiếu)"
  - "Chi tiêu cố định: recurring patterns + base average (không tính lifestyle)"
- Educational, transparent

**Pass Criteria:**
- Explanation clear
- Methodology transparent

---

# Section 7 — Goals Templates + Wizard

## TC-054: View goal templates

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Hà

**Steps:**
1. Send `/menu` → 🎯 Mục tiêu → "➕ Thêm mục tiêu"

**Expected Results:**
- Wizard shows 7 templates as buttons:
  - 🚗 Mua xe
  - 🏠 Mua nhà
  - ✈️ Du lịch
  - 🌅 Hưu trí
  - 🎓 Học vấn
  - 💒 Đám cưới
  - 🛡️ Quỹ khẩn cấp
- Plus "✏️ Tự tạo" option

**Pass Criteria:**
- All 7 templates visible
- Custom option present
- Icons consistent

---

## TC-055: Create goal from "Mua xe" template

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Hà

**Steps:**
1. From templates, tap "🚗 Mua xe"
2. Q: "Số tiền mục tiêu?" → "800tr"
3. Q: "Khi nào muốn đạt được?" → tap "2 năm"
4. Bot shows projection summary
5. Q: "Save mục tiêu này?" → tap "✅ Có"

**Expected Results:**
- Goal created:
  - template_id="buy_car"
  - name="Mua xe"
  - icon="🚗"
  - target_amount=800,000,000
  - target_date=2 years from now
  - current_amount=0
- Projection shows:
  - Required monthly savings: ~33tr
  - Feasibility: based on Hà's actual saving (8tr/month) → "needs_revision"
- Suggestions for alternatives

**Pass Criteria:**
- Goal saved correctly
- Projection visible
- Feasibility warning constructive

---

## TC-056: Create goal with custom name

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Hà

**Steps:**
1. Tap "✏️ Tự tạo"
2. Q: "Tên mục tiêu?" → "Mua máy ảnh Sony A7"
3. Q: "Số tiền?" → "60tr"
4. Q: "Khi nào?" → "1 năm"
5. Save

**Expected Results:**
- Custom goal created (no template)
- Projection: 5tr/month required → feasible (Hà saves 8tr/month)
- Bot encourages: "Mục tiêu rất khả thi 👍"

**Pass Criteria:**
- Custom path works
- No template restriction

---

## TC-057: Skip target date — open-ended goal

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Hà

**Steps:**
1. Add goal with template "🌅 Hưu trí"
2. Q: "Số tiền?" → "5 tỷ"
3. Q: "Khi nào?" → tap "Bỏ qua"

**Expected Results:**
- Goal saved without target_date
- Projection: based on actual saving rate, "Dự kiến đạt: [date X years out]"
- No feasibility warning (open-ended)

**Pass Criteria:**
- Open-ended goals supported
- Projection shows estimate

---

## TC-058: Update goal progress

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Hà

**Preconditions:** Hà has goal "Mua xe 800tr", current 50tr

**Steps:**
1. Menu → Mục tiêu → tap goal → "Cập nhật tiến độ"
2. "Số tiền mới đã có?" → "100tr"
3. Confirm

**Expected Results:**
- current_amount updated to 100tr
- Bot shows new projection:
  - "✅ Đã update. Còn cần 700tr để hoàn thành."
  - "Dự kiến đạt: [recalculated date]"
- Progress bar updates: 12.5%

**Pass Criteria:**
- Update reflects everywhere
- Projection recalculates

---

## TC-059: Goal completion celebration

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Hà

**Preconditions:** Hà has goal "Du lịch 30tr", current 28tr

**Steps:**
1. Update progress to 30tr (reach target)

**Expected Results:**
- Goal status → "completed"
- completed_at = now
- Bot celebrates: "🎉 Chúc mừng! Bạn đã đạt mục tiêu 'Du lịch'!"
- Special animation/emoji
- Suggests: "Đặt mục tiêu mới?"

**Pass Criteria:**
- Completion detected
- Celebratory message
- Suggests next step

---

## TC-060: List active goals

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Phương

**Preconditions:** Phương has 2 goals: Mua nhà + Quỹ khẩn cấp

**Steps:**
1. Menu → Mục tiêu → "📋 Mục tiêu hiện tại"

**Expected Results:**
- List shows both:
  - 🏠 Mua nhà — 5 tỷ — Progress: ▓▓░░░░░░░░ 25% (1.25 tỷ)
  - 🛡️ Quỹ khẩn cấp — 300tr — ▓▓▓▓▓▓░░░░ 67% (200tr)
- Each tappable for details

**Pass Criteria:**
- Visual progress bars
- All active goals shown

---

## TC-061: Goal detail view

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Phương

**Steps:**
1. From list, tap "Mua nhà"

**Expected Results:**
- Detail view shows:
  - Target: 5 tỷ in 5 years
  - Current: 1.25 tỷ (25%)
  - Còn cần: 3.75 tỷ
  - Required monthly: ~62.5tr/month
  - Phương's actual saving: ~30tr/month → feasibility="ambitious"
  - Suggestions for improvement
- Action buttons: [Update progress] [Edit] [Delete]

**Pass Criteria:**
- Full context visible
- Projection accurate
- Actions accessible

---

## TC-062: Edit goal

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Phương

**Steps:**
1. From detail, tap "✏️ Edit"
2. Change target: 5 tỷ → 4 tỷ (more realistic)
3. Save

**Expected Results:**
- Goal updated
- Projection recalculated
- Feasibility may improve

**Pass Criteria:**
- Edit working
- Cascading recalculations

---

## TC-063: Delete goal with confirmation

**Type:** Happy | **Story:** P3.8-S15 | **Persona:** Hà

**Steps:**
1. Tap goal → "🗑️ Delete"
2. Confirm dialog: [✅ Xóa] [❌ Hủy]

**Expected Results:**
- Confirmation prevents accidental delete
- After confirm: goal removed
- Bot acknowledges

**Pass Criteria:**
- Confirmation prompt
- Clean delete

---

# Section 8 — Goals Projection + Feasibility

## TC-064: Feasibility "easy"

**Type:** Happy | **Story:** P3.8-S14 | **Persona:** Phương

**Preconditions:** Phương saves 30tr/month

**Steps:**
1. Create goal: "Du lịch 50tr trong 1 năm"
2. View projection

**Expected Results:**
- Required monthly: 50/12 = ~4.2tr
- Ratio: 4.2/30 = 0.14
- Feasibility: "easy" (≤0.5)
- Bot framing: "Mục tiêu rất khả thi! Bạn có dư khả năng."

**Pass Criteria:**
- Easy level recognized
- Encouraging tone

---

## TC-065: Feasibility "feasible"

**Type:** Happy | **Story:** P3.8-S14 | **Persona:** Hà

**Preconditions:** Hà saves 8tr/month

**Steps:**
1. Create goal: "Mua laptop 80tr trong 1 năm"

**Expected Results:**
- Required monthly: 80/12 = ~6.7tr
- Ratio: 6.7/8 = 0.84
- Feasibility: "feasible"
- Bot: "Mục tiêu trong tầm tay 👍"

**Pass Criteria:**
- Feasible level
- Confident framing

---

## TC-066: Feasibility "stretch"

**Type:** Happy | **Story:** P3.8-S14 | **Persona:** Hà

**Steps:**
1. Create goal: "Du lịch Châu Âu 120tr trong 1 năm"

**Expected Results:**
- Required: 10tr/month
- Ratio: 10/8 = 1.25
- Feasibility: "stretch"
- Bot: "Mục tiêu thử thách. Bạn cần tiết kiệm thêm ~2tr/tháng so với hiện tại."

**Pass Criteria:**
- Stretch detected
- Specific delta shown

---

## TC-067: Feasibility "ambitious"

**Type:** Happy | **Story:** P3.8-S14 | **Persona:** Hà

**Steps:**
1. Create goal: "Mua xe 200tr trong 1 năm"

**Expected Results:**
- Required: ~17tr/month
- Ratio: 17/8 = 2.1
- Feasibility: "ambitious"
- Bot: "Mục tiêu khá thử thách. Đây là một số cách:
  1. Lùi target sang 2 năm (~8tr/tháng — khả thi)
  2. Tìm cách tăng thu nhập
  3. Giảm target amount"
- Multiple alternatives offered

**Pass Criteria:**
- Ambitious detected
- Constructive alternatives
- Not demoralizing

---

## TC-068: Feasibility "needs_revision"

**Type:** Critical | **Story:** P3.8-S14 | **Persona:** Hà

**Steps:**
1. Create goal: "Mua nhà 800tr trong 1 năm"

**Expected Results:**
- Required: 67tr/month
- Ratio: 67/8 = 8.4
- Feasibility: "needs_revision"
- Bot framing supportively:
  "Mục tiêu này hiện chưa khả thi với mức tiết kiệm 8tr/tháng. Cần ~67tr/tháng — gấp 8 lần hiện tại.
  
  Mình gợi ý:
  - 📅 Lùi target sang 8 năm (~8tr/tháng)
  - 💰 Giảm target xuống 100tr (~8tr/tháng)
  - 🚀 Tìm cách tăng thu nhập đáng kể
  
  Bạn vẫn muốn save target này chứ?"
  [✅ Vẫn save] [📅 Lùi target] [💰 Giảm amount] [❌ Hủy]

**Pass Criteria:**
- Strong warning but not harsh
- Multiple realistic options
- User has agency to override

---

## TC-069: Goal advisor query (Tier 3)

**Type:** Integration | **Story:** P3.8-S14 + agent | **Persona:** Hà

**Steps:**
1. Send: `Tôi cần làm gì để đạt mục tiêu mua xe nhanh hơn?`

**Expected Results:**
- Phase 3.7 agent routes to Tier 3 (reasoning)
- Multi-step:
  - Calls get_goals → gets "Mua xe" target
  - Calls compute_metric → saving_rate
  - Synthesizes recommendations
- Provides options:
  - Cut expenses (specific categories)
  - Increase income
  - Invest savings
- Disclaimer at end

**Pass Criteria:**
- Tier 3 used
- Multiple realistic options
- Disclaimer present

---

## TC-070: Goal projection with no income data

**Type:** Corner | **Story:** P3.8-S14 | **Persona:** Test "NoIncome"

**Steps:**
1. Create goal without income tracked yet

**Expected Results:**
- Bot recognizes missing data
- "Mình chưa biết thu nhập của bạn để dự đoán. Thêm thu nhập trước nhé?"
- Suggests adding income

**Pass Criteria:**
- Graceful with missing data
- Helpful redirection

---

# Section 9 — Agent Integration (Phase 3.7 tools)

## TC-071: Agent — get_income tool

**Type:** Integration | **Story:** P3.8-S6 | **Persona:** Phương

**Steps:**
1. Send: `Tôi có những nguồn thu gì?`

**Expected Results:**
- Agent calls get_income with no filter
- Returns all 4+ streams
- Total monthly with breakdown

**Pass Criteria:**
- Tool selected correctly
- All streams listed

---

## TC-072: Agent — forecast_cashflow tool

**Type:** Integration | **Story:** P3.8-S12 | **Persona:** Hà

**Steps:**
1. Send: `Sắp tới tài chính của tôi thế nào?`

**Expected Results:**
- Agent calls forecast_cashflow
- Returns 1-3 month forecast
- May combine with current state

**Pass Criteria:**
- Forecasting accessible via natural query

---

## TC-073: Agent — get_goals tool

**Type:** Integration | **Story:** P3.8-S15 | **Persona:** Phương

**Steps:**
1. Send: `Mình đạt được bao nhiêu phần trăm mục tiêu mua nhà?`

**Expected Results:**
- Agent calls get_goals with name filter
- Returns specific goal with progress %

**Pass Criteria:**
- Specific goal lookup works
- Progress accurate

---

## TC-074: Multi-tool query (Tier 3)

**Type:** Integration | **Story:** P3.7 + P3.8 | **Persona:** Phương

**Steps:**
1. Send: `Phân tích tổng thể tình hình tài chính của tôi và đề xuất bước tiếp theo`

**Expected Results:**
- Phase 3.7 Tier 3 reasoning agent
- Calls multiple tools:
  - get_assets (net worth)
  - get_income (income streams)
  - forecast_cashflow (future)
  - get_goals (priorities)
- Synthesizes comprehensive analysis
- Recommends 2-3 next steps
- Disclaimer present

**Pass Criteria:**
- Multi-tool reasoning works
- Phase 3.8 data integrated into agent reasoning

---

## TC-075: Agent — rental income query

**Type:** Integration | **Story:** P3.8-S6 | **Persona:** Anh Tùng

**Steps:**
1. Send: `Thu nhập từ BĐS cho thuê tháng này của tôi?`

**Expected Results:**
- Agent calls get_income with stream_type=rental
- Returns rental streams only
- Total monthly rental income

**Pass Criteria:**
- Filter by income type works
- Rental-specific query handled

---

## TC-076: Agent — runway query natural

**Type:** Integration | **Story:** P3.8-S12 | **Persona:** Hà

**Steps:**
1. Send: `Nếu thất nghiệp tôi sống được mấy tháng?`

**Expected Results:**
- Agent recognizes runway query
- Routes to forecast_cashflow with runway computation
- Returns runway analysis

**Pass Criteria:**
- Runway accessible via natural language

---

# Section 10 — Regression Tests

## TC-077: Phase 3.5 free-form queries still work

**Type:** Regression | **Story:** P3.7 (regression) | **Persona:** Phương

**Steps:**
1. Send each Phase 3.5 query:
   - "Tài sản của tôi"
   - "Chi tiêu tháng này"
   - "VNM giá bao nhiêu?"
   - "Net worth của tôi"

**Expected Results:**
- All 4 work as before
- Phase 3.8 doesn't break Phase 3.7 queries

**Pass Criteria:**
- 4/4 success
- No latency regression

---

## TC-078: Phase 3.6 menu still works

**Type:** Regression | **Story:** P3.6 (regression) | **Persona:** Hà

**Steps:**
1. Send `/menu`
2. Tap each of 5 categories
3. Verify Mục tiêu actions now functional (not stub)

**Expected Results:**
- Menu navigation intact
- Mục tiêu actions actually do things now (not "coming soon")
- Income actions show new wizard
- Recurring expense option new in Chi tiêu

**Pass Criteria:**
- Menu works
- Stubs replaced with real functionality

---

## TC-079: Phase 3.7 agent — bug fix verified

**Type:** Regression | **Story:** P3.7-S2 (the bug fix) | **Persona:** Hà

**Steps:**
1. Send: `Mã chứng khoán nào của tôi đang lãi?`
2. Verify still returns ONLY winners

**Expected Results:**
- VNM, NVDA returned (winners)
- HPG, FPT NOT in response
- Phase 3.7 fix preserved

**Pass Criteria:**
- Bug stays fixed
- Phase 3.8 changes don't regress this

---

## TC-080: Storytelling mode + recurring detection

**Type:** Regression + Integration | **Story:** P3A + P3.8-S8 | **Persona:** Phương

**Steps:**
1. Receive morning briefing
2. Tap "💬 Kể chuyện"
3. Send: `Hôm qua trả tiền điện 1.5tr`
4. Confirm transaction
5. Repeat next month with similar pattern
6. Eventually: detection should suggest "Tiền điện ~1.5tr hàng tháng"

**Expected Results:**
- Storytelling mode preserved (Phase 3A)
- Transaction recorded
- Over time, becomes detection candidate
- Phase 3A + Phase 3.8 work together

**Pass Criteria:**
- Storytelling intact
- Detection eventually triggers

---

# 📋 Test Execution Sheet Template

```
| TC ID | Title | Type | Status | Tester | Date | Notes |
|-------|-------|------|--------|--------|------|-------|
| TC-001 | Mark rental property | Happy | _____ | _____ | _____ | _____ |
| TC-030 | Receive reminder | Critical | _____ | _____ | _____ | _____ |
| TC-068 | Feasibility "needs_revision" | Critical | _____ | _____ | _____ | _____ |
... 
```

**Status values:** ✅ PASS, ⚠️ PASS WITH NOTES, ❌ FAIL, 🚫 BLOCKED, ⏭ SKIPPED

---

# 🎯 Phase 3.8 Exit Criteria Verification

After all test cases, verify Phase 3.8 exit criteria:

| Criterion | How to Verify | Critical TCs |
|-----------|---------------|--------------|
| Rental tracking complete | Section 1 | TC-001 (mark), TC-005 (yield) |
| Multi-income streams work | Section 2 | TC-012, TC-015 (aggregation) |
| Auto-detection of recurring | Section 3 | TC-021 (detect), TC-028 (no spam) |
| Reminders sent + actionable | Section 4 | TC-030 (send), TC-031 (paid) |
| Cashflow forecast meaningful | Section 5 | TC-041, TC-043 |
| Runway analysis accurate | Section 6 | TC-049, TC-050 |
| Goals templates work | Section 7 | TC-055 (template) |
| Feasibility analysis correct | Section 8 | TC-068 (needs_revision) |
| Phase 3.7 agent integrated | Section 9 | TC-074 (multi-tool) |
| No regressions | Section 10 | TC-077, TC-079 |

**🚨 Critical tests:**
- TC-030 (reminder reception — feature explicitly requested by user)
- TC-031 (reminder action — completes the loop)
- TC-068 (feasibility framing — supportive not harsh)
- TC-079 (Phase 3.7 bug fix preserved)

If ALL critical PASS → ✅ Ship to all users.

---

# 🐛 Common Failure Modes — What to Watch

## 1. Rental Income Double-Counting
**Symptom:** Total income inflated.  
**Cause:** Manual transaction "thuê nhận" + auto income stream both counted.  
**Action:** Verify auto-link works, check for duplicates.

## 2. Recurring Detection False Positives
**Symptom:** Bot suggests "Bún chả 50k hàng tháng".  
**Cause:** Heuristic too loose.  
**Action:** Tighten amount tolerance + merchant similarity check.

## 3. Reminder Spam
**Symptom:** User receives 5 reminders one morning.  
**Cause:** No bundling.  
**Action:** Verify bundling logic, single message for same-day.

## 4. Forecast Over-Confidence
**Symptom:** "Tháng 8 sẽ có chính xác 8,567,234đ".  
**Cause:** Single number without confidence.  
**Action:** Always show confidence %, prefer ranges.

## 5. Goal Feasibility Demoralizing
**Symptom:** User upset by "needs_revision" message.  
**Cause:** Harsh tone.  
**Action:** Always offer alternatives, supportive framing.

## 6. Phase 3.7 Agent Doesn't See New Data
**Symptom:** Asks "rental income" → bot says "no data".  
**Cause:** New tools not registered or service not extended.  
**Action:** Verify ToolRegistry includes all new tools.

## 7. Auto-Created Income Not Updating
**Symptom:** User changed rent 15→17tr but income stream still shows 15tr.  
**Cause:** Cascade update missing.  
**Action:** Verify rental update propagates to income stream.

---

# 📊 Test Coverage Summary

```
Total test cases: 80

By Section:
  S1 Rental Property:        10 cases (TC-001 to TC-010)
  S2 Multi-Income Streams:   10 cases (TC-011 to TC-020)
  S3 Recurring Auto-Detect:   8 cases (TC-021 to TC-028)
  S4 Recurring + Reminders:  12 cases (TC-029 to TC-040)
  S5 Cashflow Forecasting:    8 cases (TC-041 to TC-048)
  S6 Runway Analysis:         5 cases (TC-049 to TC-053)
  S7 Goals Templates+Wizard: 10 cases (TC-054 to TC-063)
  S8 Goals Projection:        7 cases (TC-064 to TC-070)
  S9 Agent Integration:       6 cases (TC-071 to TC-076)
  S10 Regression:             4 cases (TC-077 to TC-080)

By Type:
  Happy:               ~38 cases (47%)
  Integration:         ~12 cases (15%)
  Critical:             ~5 cases (6%)
  Corner:               ~8 cases (10%)
  Regression:           ~4 cases (5%)
  Performance/Other:   ~13 cases (17%)
```

---

# 🚀 Final Notes for Tester

## Before Testing
1. Read `phase-3.8-detailed.md` to understand all 5 components
2. Read `phase-3.8-issues.md` for context per story
3. Set up 4 personas with **specific Phase 3.8 data** (see Test Data Setup section)
4. Verify cron jobs running:
   - RecurringDetector (nightly)
   - ReminderScheduler (daily 9 AM)
5. Have iPhone, Android, Desktop Telegram ready

## During Testing — Order Matters
1. **Section 1 + 2 first** (rental + income foundation)
2. **Section 3** (auto-detection — needs history)
3. **Section 4** (manual recurring + reminders — uses Section 3 patterns)
4. **Section 5 + 6** (forecast + runway — needs Section 2 data)
5. **Section 7 + 8** (goals — uses Section 5 forecasts)
6. **Section 9** (agent integration — verifies Phase 3.7 + 3.8 together)
7. **Section 10** (regression — must pass)

## Reminder Tests Need Time

Section 4 reminder tests (TC-030, etc.) require:
- Setting up patterns
- Waiting for cron to run (or manual trigger)
- Verifying timing (2 days before due)

→ Allocate 2-3 days for full Section 4 testing.

## CRITICAL Tests You CANNOT Skip

| TC | Why Critical |
|----|--------------|
| **TC-030** | The reminder feature — explicit user request |
| **TC-031** | Reminder → transaction loop closure |
| **TC-034** | Bundled reminders (don't spam) |
| **TC-068** | Goal feasibility framing (supportive) |
| **TC-074** | Phase 3.7 agent integration with new data |
| **TC-077-080** | Regression — protect Phase 3.5/3.6/3.7 |

If ANY critical fails, **iterate before ship**.

---

**Phase 3.8 = foundation completion. After this, Twin (Phase 4) builds on solid ground. The agent has full picture of user's financial life. 💚🏗️🚀**
