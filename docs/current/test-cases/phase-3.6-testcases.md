# Phase 3.6 — Manual Test Cases (Telegram Bot)

> **Purpose:** Comprehensive test cases for manual tester to validate Phase 3.6 (Menu UX Revamp) on Telegram bot.  
> **Tester Profile:** No source code access. Tests via Telegram chat interface + Mini App for verification.  
> **Reference:** [phase-3.6-detailed.md](./phase-3.6-detailed.md), [phase-3.6-issues.md](./phase-3.6-issues.md)

---

## 📋 How to Use This Document

### Test Case Structure

Each test case follows this format:

```
TC-XXX: [Title]
Type: Happy | Corner | Regression | Integration | Migration | Visual
Story: P3.6-Sn (links to issue)
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

**Reuse 4 personas from Phase 3.5** test cases:
- **Minh** (Starter, 17tr net worth)
- **Hà** (Young Professional, 140tr)
- **Phương** (Mass Affluent, 4.5 tỷ)
- **Anh Tùng** (HNW, 13 tỷ)

See `phase-3.5-test-cases.md` for full persona setup details.

**Additional setup for Phase 3.6:**
- Ensure all 4 personas have Phase 3.5 deployed (intent classifier active)
- Each persona should have ≥1 active goal (for Mục tiêu testing)
- Each persona should have ≥1 transaction last 30 days (for Chi tiêu testing)

---

## 🔧 Environment Requirements

- **Bot version:** Phase 3.6 deployed
- **Telegram client:** Test on iPhone, Android, Desktop (3 form factors)
- **Network:** Stable + slow connection variants
- **Database:** 4 personas pre-populated as above
- **Pre-deploy:** Verify Phase 3A + 3.5 still functional first

---

## 📊 Test Coverage Overview

| Section | Test Cases | Type Distribution |
|---------|-----------|-------------------|
| Section 1: Main Menu Display | ~10 | Happy + Visual |
| Section 2: Sub-Menu Navigation | ~15 | Happy + Visual |
| Section 3: Action Triggering | ~15 | Happy + Integration |
| Section 4: Adaptive Intros | ~10 | Visual |
| Section 5: Free-form Coexistence | ~5 | Integration |
| Section 6: Migration & Cutover | ~5 | Migration |
| Section 7: Corner & Negative | ~10 | Corner + Negative |
| Section 8: Regression | ~5 | Regression |
| **Total** | **~75** | |

---

# Section 1 — Main Menu Display

## TC-001: /menu command — basic invocation

**Type:** Happy | **Story:** P3.6-S3 | **Persona:** Hà

**Preconditions:**
- Phase 3.6 deployed
- Hà account active

**Steps:**
1. Open Telegram chat with Bé Tiền
2. Type and send: `/menu`
3. Wait for response

**Expected Results:**
- Bot replies within 1 second
- Message contains:
  - Title with "Bé Tiền" + Hà's name
  - Brief intro text (2-4 lines)
  - 5 buttons visible: "💎 Tài sản", "💸 Chi tiêu", "💰 Dòng tiền", "🎯 Mục tiêu", "📊 Thị trường"
  - Hint section with example free-form queries
- Buttons in 2-column grid layout (last button alone in last row OR balanced)
- No mention of "Quét Gmail" or other deprecated features

**Pass Criteria:**
- All 5 categories visible
- Hint about free-form alternative present
- Response time <1s
- Layout fits in 1 mobile screen without scroll

**Fail Examples:**
- ❌ Old menu shown (8 flat buttons including "Quét Gmail")
- ❌ Some categories missing
- ❌ "Finance Assistant" title (V1 branding)

---

## TC-002: Bot menu button (Telegram corner) — commands list

**Type:** Happy | **Story:** P3.6-S8 | **Persona:** Any

**Steps:**
1. In chat with Bé Tiền, tap the **menu button at bottom-left corner of input area** (this is Telegram's native bot menu button, looks like a "/" icon or a 3-line menu icon)
2. Observe the popup list

**Expected Results:**
- Popup shows 4 commands:
  - `/start` — "Bắt đầu / Onboarding"
  - `/menu` — "Menu chính"
  - `/help` — "Hướng dẫn sử dụng"
  - `/dashboard` — "Mở Mini App dashboard"
- No deprecated commands (e.g., old commands from V1)

**Pass Criteria:**
- Exactly 4 commands listed
- Descriptions in Vietnamese
- Tapping each command works

**Note:** If commands don't appear, Telegram client may need restart (cache refresh).

---

## TC-003: Main menu — title contains user's name

**Type:** Happy | **Story:** P3.6-S2 | **Persona:** Hà

**Steps:**
1. Send: `/menu`
2. Read title line

**Expected Results:**
- Title format: "👋 Bé Tiền — Trợ lý tài chính của Hà" (or similar)
- User's `display_name` appears in title

**Pass Criteria:**
- Name "Hà" visible in title

---

## TC-004: Main menu — hint section visible

**Type:** Happy | **Story:** P3.6-S1 | **Persona:** Hà

**Steps:**
1. Send: `/menu`
2. Scroll to bottom of message (if needed)

**Expected Results:**
- Hint section starts with "💡 Mẹo:"
- Lists 3 example free-form queries
- Examples are realistic (e.g., "tài sản của tôi có gì?")
- Encourages free-form usage

**Pass Criteria:**
- Hint visible
- 3 examples present
- Tone matches Bé Tiền personality

---

## TC-005: Main menu — buttons in 2-column grid

**Type:** Visual | **Story:** P3.6-S2 | **Persona:** Hà

**Steps:**
1. Send: `/menu`
2. Observe button layout

**Expected Results:**
- 5 buttons arranged in grid:
  ```
  [💎 Tài sản]   [💸 Chi tiêu]
  [💰 Dòng tiền] [🎯 Mục tiêu]
  [📊 Thị trường]
  ```
- Last row has 1 button OR centered
- Buttons evenly spaced

**Pass Criteria:**
- Visual layout matches above
- No buttons cropped or wrapped awkwardly

---

## TC-006: Main menu — Markdown rendering

**Type:** Visual | **Story:** P3.6-S2 | **Persona:** Phương

**Steps:**
1. Send: `/menu`
2. Examine text formatting

**Expected Results:**
- Bold text renders correctly (no `**` visible)
- Emojis display properly
- Line breaks preserved
- No raw Markdown syntax leaking

**Pass Criteria:**
- Clean readable text
- No `**word**` or `_word_` artifacts

**Fail Example:**
- ❌ Title shows literal `**👋 Bé Tiền**` instead of bold

---

## TC-007: Main menu — different layouts on different devices

**Type:** Visual | **Story:** P3.6-S2 | **Persona:** Hà

**Steps:**
1. Send `/menu` from iPhone
2. Send `/menu` from Android
3. Send `/menu` from Telegram Desktop
4. Compare layouts

**Expected Results:**
- All 3 devices show same menu structure
- Buttons fit screen width on all devices
- No text overflow on smaller screens (iPhone SE)

**Pass Criteria:**
- Visual consistency across 3 devices
- No clipping or overflow

---

## TC-008: Main menu — response time

**Type:** Performance | **Story:** P3.6-S3 | **Persona:** Phương (most data)

**Steps:**
1. Use stopwatch or note send time
2. Send `/menu`
3. Note time menu appears
4. Calculate delay
5. Repeat 5 times, average

**Expected Results:**
- Response time <1 second on average
- Worst case <2 seconds

**Pass Criteria:**
- Average <1s
- p99 <2s

---

## TC-009: Main menu — fresh state on every invocation

**Type:** Corner | **Story:** P3.6-S3 | **Persona:** Hà

**Steps:**
1. Send `/menu`
2. Tap "💎 Tài sản" → sub-menu shows
3. Don't tap anything else
4. Send `/menu` again (new command)
5. Observe

**Expected Results:**
- New main menu appears as new message (NOT edit of old sub-menu)
- Old sub-menu remains in chat history
- No state confusion

**Pass Criteria:**
- /menu always renders main menu fresh
- Doesn't accidentally edit existing message

---

## TC-010: Main menu — handles missing display_name

**Type:** Corner | **Story:** P3.6-S2 | **Persona:** New test user "NoName"

**Preconditions:** Create test user with `display_name = NULL`

**Steps:**
1. Send `/menu` from NoName account

**Expected Results:**
- Bot doesn't crash
- Title falls back to "bạn" or similar generic
- Menu otherwise functional

**Pass Criteria:**
- No exception
- Menu usable
- Graceful fallback for missing name

---

# Section 2 — Sub-Menu Navigation

## TC-011: Tap "💎 Tài sản" — sub-menu appears (edit in place)

**Type:** Happy | **Story:** P3.6-S4 | **Persona:** Phương

**Steps:**
1. Send `/menu`
2. Tap "💎 Tài sản" button
3. Observe what happens

**Expected Results:**
- Bot edits the same message (NOT new message)
- Message now shows:
  - Title: "💎 TÀI SẢN"
  - Intro paragraph (3-5 lines)
  - 5 action buttons (Tổng tài sản, Báo cáo, Thêm, Sửa, Tư vấn) + 1 "◀️ Quay về"
  - Hint section
- Loading spinner dismissed quickly

**Pass Criteria:**
- Same message bubble (not new)
- All 6 buttons present (5 actions + back)
- Smooth transition

---

## TC-012: Tap "◀️ Quay về" — return to main menu

**Type:** Happy | **Story:** P3.6-S4 | **Persona:** Phương

**Preconditions:** Continue from TC-011 (in Tài sản sub-menu)

**Steps:**
1. Tap "◀️ Quay về" button
2. Observe

**Expected Results:**
- Bot edits same message
- Main menu re-appears (5 categories)
- Original message bubble preserved (not new)

**Pass Criteria:**
- Back navigation works
- Edit-in-place maintained

---

## TC-013: Navigate all 5 sub-menus

**Type:** Happy | **Story:** P3.6-S4 | **Persona:** Phương

**Steps:**
1. Send `/menu`
2. Tap "💎 Tài sản" → verify sub-menu loads
3. Tap "◀️ Quay về"
4. Tap "💸 Chi tiêu" → verify sub-menu
5. Tap "◀️ Quay về"
6. Tap "💰 Dòng tiền" → verify sub-menu
7. Tap "◀️ Quay về"
8. Tap "🎯 Mục tiêu" → verify sub-menu
9. Tap "◀️ Quay về"
10. Tap "📊 Thị trường" → verify sub-menu

**Expected Results:**
- All 5 sub-menus load successfully
- Each has unique title and buttons
- "Quay về" works from each
- Throughout test, only 1 message bubble used (edit-in-place)

**Pass Criteria:**
- All 5 sub-menus reachable
- Navigation smooth
- Chat history shows minimal clutter

---

## TC-014: Sub-menu Tài sản — verify all expected buttons

**Type:** Happy | **Story:** P3.6-S1 | **Persona:** Hà

**Steps:**
1. /menu → 💎 Tài sản
2. Count and identify buttons

**Expected Results:**
- Exactly 6 buttons:
  - 📊 Tổng tài sản
  - 📈 Báo cáo chi tiết (or similar)
  - ➕ Thêm tài sản
  - ✏️ Sửa tài sản
  - 💡 Tư vấn tối ưu
  - ◀️ Quay về

**Pass Criteria:**
- 6 buttons exactly
- Labels match spec (P3.6-S1 YAML)

---

## TC-015: Sub-menu Chi tiêu — verify all expected buttons

**Type:** Happy | **Story:** P3.6-S1 | **Persona:** Hà

**Steps:**
1. /menu → 💸 Chi tiêu
2. Count and identify buttons

**Expected Results:**
- Exactly 5 buttons:
  - ➕ Thêm chi tiêu
  - 📷 OCR hoá đơn
  - 📊 Báo cáo chi tiêu
  - 🏷️ Theo phân loại
  - ◀️ Quay về

**Pass Criteria:**
- 5 buttons exactly

---

## TC-016: Sub-menu Dòng tiền — verify buttons

**Type:** Happy | **Story:** P3.6-S1 | **Persona:** Phương

**Steps:**
1. /menu → 💰 Dòng tiền
2. Count buttons

**Expected Results:**
- Exactly 5 buttons:
  - 📊 Tổng quan dòng tiền
  - 💼 Thu nhập
  - 📉 Chi tiêu vs Thu nhập
  - 💎 Tỷ lệ tiết kiệm
  - ◀️ Quay về

**Pass Criteria:**
- 5 buttons exactly

---

## TC-017: Sub-menu Mục tiêu — verify buttons

**Type:** Happy | **Story:** P3.6-S1 | **Persona:** Hà

**Steps:**
1. /menu → 🎯 Mục tiêu
2. Count buttons

**Expected Results:**
- Exactly 5 buttons:
  - 📋 Mục tiêu hiện tại
  - ➕ Thêm mục tiêu
  - ✏️ Cập nhật tiến độ
  - 💡 Gợi ý lộ trình
  - ◀️ Quay về

**Pass Criteria:**
- 5 buttons exactly

---

## TC-018: Sub-menu Thị trường — verify buttons

**Type:** Happy | **Story:** P3.6-S1 | **Persona:** Phương

**Steps:**
1. /menu → 📊 Thị trường
2. Count buttons

**Expected Results:**
- Exactly 6 buttons:
  - 🇻🇳 VN-Index hôm nay
  - 📈 Cổ phiếu quan tâm
  - ₿ Crypto
  - 🥇 Vàng SJC
  - 💡 Cơ hội đầu tư
  - ◀️ Quay về

**Pass Criteria:**
- 6 buttons exactly

---

## TC-019: Sub-menu — hint section present

**Type:** Happy | **Story:** P3.6-S1 | **Persona:** Hà

**Steps:**
1. /menu → tap each of 5 categories one by one
2. For each sub-menu, verify hint section

**Expected Results:**
- Each sub-menu has hint at bottom: "💡 Hoặc hỏi nhanh:"
- Each hint has 3 examples
- Examples are **specific to that category** (not generic)
- Example: Tài sản hint shows asset-related queries; Chi tiêu hint shows expense-related

**Pass Criteria:**
- All 5 sub-menus have hints
- Hints are category-specific
- Examples make sense

---

## TC-020: Sub-menu intro — appropriate length

**Type:** Visual | **Story:** P3.6-S1 | **Persona:** Phương

**Steps:**
1. /menu → 💎 Tài sản
2. Read intro paragraph
3. Count approximate word count
4. Verify fits 1 mobile screen with buttons

**Expected Results:**
- Intro is 30-80 words (not too short, not too long)
- Together with title + buttons + hint, fits 1 mobile screen
- No need to scroll for HNW intro

**Pass Criteria:**
- Length appropriate
- Mobile-friendly layout
- All elements visible without scroll

---

# Section 3 — Action Triggering

## TC-021: Tap "📊 Tổng tài sản" — shows net worth

**Type:** Integration | **Story:** P3.6-S5 | **Persona:** Phương

**Preconditions:** Phương has 5 assets across types

**Steps:**
1. /menu → 💎 Tài sản → 📊 Tổng tài sản
2. Wait for response

**Expected Results:**
- Bot shows net worth response (similar to free-form "tài sản của tôi có gì")
- Total ~4.5 tỷ displayed
- Breakdown by asset type
- Personal tone with "Phương" or "anh"

**Pass Criteria:**
- Action triggers correct handler
- Data accurate
- Same quality as free-form query equivalent

---

## TC-022: Tap "➕ Thêm tài sản" — wizard starts

**Type:** Integration | **Story:** P3.6-S5 | **Persona:** Minh

**Steps:**
1. /menu → 💎 Tài sản → ➕ Thêm tài sản
2. Observe response

**Expected Results:**
- Bot starts asset entry wizard (Phase 3A flow)
- Shows asset type buttons (Tiền mặt, Chứng khoán, BĐS, Crypto, Vàng, Khác)
- Wizard state set correctly

**Pass Criteria:**
- Wizard launches from menu
- Same wizard as `/add_asset` command
- Can complete wizard normally

---

## TC-023: Complete wizard from menu — full flow

**Type:** Integration | **Story:** P3.6-S5 | **Persona:** Minh

**Preconditions:** Continue from TC-022 (in wizard)

**Steps:**
1. Tap "💵 Tiền mặt / TK"
2. Tap subtype "🏦 Tiết kiệm ngân hàng"
3. When prompted, send: `MoMo 5tr`
4. Tap "✅ Đúng" on confirmation

**Expected Results:**
- Full wizard flow works
- Asset created (verify in Mini App or via /menu → Tổng tài sản)
- Wizard exits cleanly

**Pass Criteria:**
- Wizard completes successfully when started from menu
- No state issues
- Data persisted

---

## TC-024: Tap "📷 OCR hoá đơn" — prompts for image

**Type:** Integration | **Story:** P3.6-S5 | **Persona:** Hà

**Steps:**
1. /menu → 💸 Chi tiêu → 📷 OCR hoá đơn
2. Read response

**Expected Results:**
- Bot sends instruction message: "Gửi ảnh hóa đơn cho mình nhé 📷" (or similar)
- Doesn't try to start image upload (Telegram doesn't support that)
- Just instructs user to send image

**Pass Criteria:**
- Clear instruction
- User can then send image normally
- OCR processes image when sent

---

## TC-025: Tap "📊 Báo cáo chi tiêu" — shows expense report

**Type:** Integration | **Story:** P3.6-S5 | **Persona:** Phương

**Steps:**
1. /menu → 💸 Chi tiêu → 📊 Báo cáo chi tiêu

**Expected Results:**
- Bot shows current month expense summary
- Total + breakdown by category
- Top transactions

**Pass Criteria:**
- Same content as free-form "chi tiêu tháng này"

---

## TC-026: Tap "🏷️ Theo phân loại" — shows category breakdown

**Type:** Integration | **Story:** P3.6-S5 | **Persona:** Phương

**Steps:**
1. /menu → 💸 Chi tiêu → 🏷️ Theo phân loại

**Expected Results:**
- Bot shows expenses grouped by category
- Each category: total + count
- Sorted by spending desc
- May have inline keyboard to drill into specific category

**Pass Criteria:**
- Category breakdown clear
- Numbers accurate

---

## TC-027: Tap "📊 Tổng quan dòng tiền"

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Phương

**Steps:**
1. /menu → 💰 Dòng tiền → 📊 Tổng quan dòng tiền

**Expected Results:**
- Bot shows cashflow summary
- Total income, total expense, net (savings)
- This month or current period

**Pass Criteria:**
- Cashflow calculation correct
- Format readable

---

## TC-028: Tap "💼 Thu nhập"

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Phương

**Steps:**
1. /menu → 💰 Dòng tiền → 💼 Thu nhập

**Expected Results:**
- Bot lists income streams (Phương has lương + dividend)
- Each shows monthly amount
- Total monthly income

**Pass Criteria:**
- All streams listed
- Same as free-form "thu nhập của tôi"

---

## TC-029: Tap "💎 Tỷ lệ tiết kiệm"

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Hà

**Steps:**
1. /menu → 💰 Dòng tiền → 💎 Tỷ lệ tiết kiệm

**Expected Results:**
- Bot calculates and shows saving rate %
- Format: "Tỷ lệ tiết kiệm tháng này: X%" 
- May include comparison vs healthy benchmark (20-30%)
- May show: "Bạn tiết kiệm được Xtr/Ytr thu nhập"

**Pass Criteria:**
- Calculation correct
- Encouraging tone

---

## TC-030: Tap "📋 Mục tiêu hiện tại"

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Hà

**Preconditions:** Hà has goal "Mua xe" 800tr, current 50tr

**Steps:**
1. /menu → 🎯 Mục tiêu → 📋 Mục tiêu hiện tại

**Expected Results:**
- Bot lists active goals
- Shows: name, target, current progress, %
- Hà's goal "Mua xe" appears
- 50/800tr = ~6%

**Pass Criteria:**
- Goal data correct
- Progress visualization clear

---

## TC-031: Tap "➕ Thêm mục tiêu"

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Minh

**Steps:**
1. /menu → 🎯 Mục tiêu → ➕ Thêm mục tiêu

**Expected Results:**
- Either: Add-goal wizard starts (if implemented)
- Or: "🚧 Tính năng đang phát triển" message with helpful instruction
- Doesn't crash silently

**Pass Criteria:**
- Either fully functional OR graceful coming-soon
- User informed

---

## TC-032: Tap "🇻🇳 VN-Index hôm nay"

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Phương

**Steps:**
1. /menu → 📊 Thị trường → 🇻🇳 VN-Index hôm nay

**Expected Results:**
- Bot shows VN-Index value
- Change from previous close
- Optional: top gainer/loser

**Pass Criteria:**
- Same as free-form "VN-Index hôm nay"
- Data displayed cleanly

---

## TC-033: Tap "📈 Cổ phiếu quan tâm" — user has stocks

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Hà (owns VNM, HPG)

**Steps:**
1. /menu → 📊 Thị trường → 📈 Cổ phiếu quan tâm

**Expected Results:**
- Bot lists stocks Hà owns: VNM, HPG
- For each: current price, change %, current value
- May include watchlist stocks if any

**Pass Criteria:**
- Owned stocks shown with personal context
- Quantities correct

---

## TC-034: Tap "₿ Crypto"

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Phương

**Steps:**
1. /menu → 📊 Thị trường → ₿ Crypto

**Expected Results:**
- Bot shows top crypto prices (BTC, ETH at minimum)
- May include user's crypto holdings (Phương has 250tr crypto)

**Pass Criteria:**
- Crypto data shown
- No errors

---

## TC-035: Tap "💡 Cơ hội đầu tư" — advisory

**Type:** Integration | **Story:** P3.6-S6 | **Persona:** Phương

**Steps:**
1. /menu → 📊 Thị trường → 💡 Cơ hội đầu tư
2. Wait (LLM call, may take 3-5 seconds)

**Expected Results:**
- Bot calls advisory handler with "cơ hội đầu tư mới" context
- Response references Phương's portfolio
- Provides 2-3 outward-looking investment options
- **Disclaimer present:** "Đây là gợi ý dựa trên data cá nhân, không phải lời khuyên đầu tư chuyên nghiệp"
- No specific stock recommendations

**Pass Criteria:**
- Advisory response received
- Disclaimer present
- No legal/compliance violations

---

## TC-036: Tap "💡 Tư vấn tối ưu" (in Tài sản) — inward advisor

**Type:** Integration | **Story:** P3.6-S5 | **Persona:** Phương

**Steps:**
1. /menu → 💎 Tài sản → 💡 Tư vấn tối ưu

**Expected Results:**
- Bot calls advisory handler with "rebalance portfolio" context
- Response analyzes Phương's CURRENT allocation
- Suggestions inward-looking (rebalance, diversify existing assets)
- Different from "Cơ hội đầu tư" (which is outward)
- Disclaimer present

**Pass Criteria:**
- Inward focus (existing portfolio)
- Different angle from "Cơ hội đầu tư"

**Note for tester:** Run TC-035 and TC-036 sequentially with same user. Compare responses — should feel different (rebalance vs new opportunities).

---

## TC-037: All 23 actions clickable — sweep test

**Type:** Happy | **Story:** P3.6-S5 + S6 | **Persona:** Phương

**Steps:**
1. /menu
2. For each of 5 categories, tap each of 4-5 actions
3. Note which work, which show "coming soon", which crash

**Expected Results:**
- All ~23 actions handled (real result OR "coming soon" message)
- Zero crashes / silent failures
- Document per-action status:
  - ✅ Fully functional
  - 🚧 Coming soon (graceful)
  - ❌ Broken (escalate)

**Pass Criteria:**
- 0 crashes
- Most actions ✅ functional, some 🚧 acceptable, 0 ❌

---

## TC-038: Action callbacks — back button after action

**Type:** Corner | **Story:** P3.6-S5 | **Persona:** Phương

**Steps:**
1. /menu → 💎 Tài sản → 📊 Tổng tài sản
2. After response shown, tap... wait, is there back button?

**Expected Results:**
- Action response may include back button "◀️ Về Tài sản" or similar
- Or: User uses /menu to start over
- Document the actual UX (depends on design)

**Pass Criteria:**
- User has clear path back to menu after seeing data

**Note:** This is UX consideration. If no back button, document as feature request for Phase 4.

---

## TC-039: Sequential actions don't conflict

**Type:** Corner | **Story:** P3.6-S4 | **Persona:** Hà

**Steps:**
1. /menu → 💎 Tài sản → 📊 Tổng tài sản (action shows result)
2. /menu → 💸 Chi tiêu → 📊 Báo cáo chi tiêu

**Expected Results:**
- Both queries answered
- No state confusion
- Each menu invocation works independently

**Pass Criteria:**
- Multiple actions in sequence work cleanly

---

## TC-040: Action triggers free-form-equivalent response

**Type:** Integration | **Story:** P3.6-S5 | **Persona:** Phương

**Steps:**
1. Send free-form: `tổng tài sản của tôi` → note response
2. /menu → 💎 Tài sản → 📊 Tổng tài sản → note response
3. Compare both responses

**Expected Results:**
- Both responses show same net worth data
- Format may differ slightly (menu may include "from menu" context)
- Core data identical

**Pass Criteria:**
- Menu action and free-form give equivalent answers
- No data inconsistency

---

# Section 4 — Adaptive Intros (Wealth Level)

## TC-041: Starter intro — Minh

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** Minh (17tr)

**Steps:**
1. From Minh account, send: `/menu`
2. Read main menu intro carefully
3. Take screenshot

**Expected Results:**
- Title: "Trợ lý tài chính của Minh" (NOT "CFO")
- Intro text encouraging, simple language
- May mention "xây nền tảng", "bắt đầu từng bước"
- No advanced terms (allocation, performance metrics)
- Tone: warm, beginner-friendly

**Pass Criteria:**
- Starter-appropriate language
- No HNW-level jargon

---

## TC-042: Young Professional intro — Hà

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** Hà (140tr)

**Steps:**
1. From Hà account, send: `/menu`
2. Read intro
3. Take screenshot

**Expected Results:**
- Title: "Trợ lý tài chính của Hà"
- Intro slightly more sophisticated than Minh's
- May mention "xây danh mục đầu tư"
- Encouraging but more confident tone

**Pass Criteria:**
- Different from Minh's intro
- Different from Phương's intro

---

## TC-043: Mass Affluent intro — Phương

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** Phương (4.5 tỷ)

**Steps:**
1. From Phương account, send: `/menu`
2. Read intro
3. Take screenshot

**Expected Results:**
- Title: "Trợ lý CFO cá nhân của Phương" or "Personal CFO"
- Intro mentions "tối ưu hóa", "quyết định tài chính thông minh"
- Professional tone
- Refers to Phương as "anh" or "chị" (respectful)

**Pass Criteria:**
- "CFO" appears in title
- Professional tone
- Different from Hà and Anh Tùng

---

## TC-044: HNW intro — Anh Tùng

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** Anh Tùng (13 tỷ)

**Steps:**
1. From Anh Tùng account, send: `/menu`
2. Read intro
3. Take screenshot

**Expected Results:**
- Title: "Personal CFO của anh/chị Tùng" or similar
- Most professional tone
- May mention "performance metrics", "allocation"
- Most concise (HNW users want efficiency)

**Pass Criteria:**
- Advanced level language
- Concise
- Most distinct from Starter

---

## TC-045: Side-by-side comparison — main menu intros

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** All 4

**Steps:**
1. Run TC-041 through TC-044 (collect 4 screenshots)
2. Place 4 screenshots side-by-side
3. Compare

**Expected Results:**
- 4 distinct intro texts
- Visual progression: simple (Minh) → professional (Anh Tùng)
- Tone difference noticeable
- Same buttons across all 4

**Pass Criteria:**
- Clear visual diff between levels
- Buttons identical
- Each "feels right" for its level

**Note for tester:** This is the critical adaptive UX test. If you can't tell who's who from intro, adaptive logic isn't working.

---

## TC-046: Sub-menu Tài sản — adaptive across 4 levels

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** All 4

**Steps:**
1. From each persona, navigate /menu → 💎 Tài sản
2. Take screenshot of each sub-menu
3. Compare 4 screenshots

**Expected Results:**
- Same buttons (5 actions + back)
- Different intro paragraphs (4 levels)
- Starter encouraging: "mỗi tài sản bạn thêm sẽ giúp..."
- HNW concise: "Tổng quan tài sản và performance metrics..."

**Pass Criteria:**
- 4 distinct intros
- Buttons identical
- Visual diff confirms adaptive working

---

## TC-047: Sub-menu Chi tiêu — adaptive

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** All 4

**Steps:**
1. Each persona: /menu → 💸 Chi tiêu
2. Compare intros

**Expected Results:**
- Different intros for each level
- Common theme but adaptive language

**Pass Criteria:**
- Adaptive logic visible

---

## TC-048: Sub-menu Dòng tiền — adaptive

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** All 4

**Steps:**
1. Each persona: /menu → 💰 Dòng tiền
2. Compare intros

**Expected Results:**
- Starter: simple cashflow explanation
- HNW: passive income, runway analysis mention

**Pass Criteria:**
- Concept mentions adapt to level

---

## TC-049: Sub-menu Mục tiêu — adaptive

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** All 4

**Steps:**
1. Each persona: /menu → 🎯 Mục tiêu
2. Compare intros

**Expected Results:**
- Starter: small goals examples (10tr, xe máy)
- HNW: long-term, retirement, estate

**Pass Criteria:**
- Goal scope adapts to level

---

## TC-050: Sub-menu Thị trường — adaptive

**Type:** Visual | **Story:** P3.6-S7 | **Persona:** All 4

**Steps:**
1. Each persona: /menu → 📊 Thị trường
2. Compare intros

**Expected Results:**
- Starter: VNM, VIC popular tickers
- HNW: deep market analysis

**Pass Criteria:**
- Sophistication adapts

---

## TC-051: Boundary case — 29.9tr (just below Starter cap)

**Type:** Corner | **Story:** P3.6-S7 | **Persona:** New "TestEdge" with 29,999,999đ

**Preconditions:** Create test user with net worth exactly 29tr 999k

**Steps:**
1. /menu from this account
2. Read intro

**Expected Results:**
- Treated as Starter level
- Intro matches Starter style

**Pass Criteria:**
- 29.9tr → Starter (not Young Prof)

---

## TC-052: Boundary case — 30tr exact

**Type:** Corner | **Story:** P3.6-S7 | **Persona:** TestEdge updated to 30,000,000đ

**Steps:**
1. Adjust net worth to exactly 30tr
2. /menu

**Expected Results:**
- Treated as Young Professional (not Starter)
- Intro matches Young Prof style

**Pass Criteria:**
- 30tr → Young Prof (boundary deterministic)

---

## TC-053: Adaptive level changes during session

**Type:** Corner | **Story:** P3.6-S7 | **Persona:** Hà

**Steps:**
1. /menu (Hà at 140tr — Young Prof)
2. Note intro
3. Add a fake asset of 100tr to push Hà to 240tr (Mass Affluent territory)
4. /menu again
5. Compare intro

**Expected Results:**
- Second /menu shows Mass Affluent intro (different from first)
- No caching issue
- Wealth level recalculated

**Pass Criteria:**
- Level updates dynamically with net worth changes

**Note:** This tests caching strategy. If cache too aggressive, level lag is bad UX.

---

## TC-054: Performance impact of adaptive logic

**Type:** Performance | **Story:** P3.6-S7 | **Persona:** Phương

**Steps:**
1. /menu → time response (with adaptive)
2. Repeat 5 times, average

**Expected Results:**
- Response time still <1s with adaptive logic
- Wealth level detection adds <100ms to render

**Pass Criteria:**
- No noticeable slowdown vs basic menu

---

## TC-055: Bot menu button — unchanged across levels

**Type:** Visual | **Story:** P3.6-S8 | **Persona:** All 4

**Steps:**
1. Tap bot menu button (corner) from each persona
2. Compare lists

**Expected Results:**
- Same 4 commands across all levels (no adaptive here)
- Bot menu button is global, not per-user

**Pass Criteria:**
- Consistent commands list

---

# Section 5 — Free-Form Coexistence

## TC-056: Open menu, then send free-form query

**Type:** Integration | **Story:** P3.6-S9 | **Persona:** Hà

**Steps:**
1. Send `/menu` → main menu visible
2. Without tapping, send text: `tài sản của tôi có gì?`
3. Wait

**Expected Results:**
- Menu remains visible (not auto-deleted)
- Bot answers query in NEW message (below menu)
- No conflict

**Pass Criteria:**
- Both messages coexist
- Query answered correctly

---

## TC-057: Send query, then open menu

**Type:** Integration | **Story:** P3.6-S9 | **Persona:** Hà

**Steps:**
1. Send `tài sản của tôi có gì?` → bot replies
2. Send `/menu` → menu appears

**Expected Results:**
- Both messages in chat
- Menu opens normally below query response

**Pass Criteria:**
- No conflict between query and menu

---

## TC-058: Free-form query while menu sub-page open

**Type:** Integration | **Story:** P3.6-S9 | **Persona:** Phương

**Steps:**
1. /menu → 💎 Tài sản (sub-menu open)
2. Send text: `chi tiêu tháng này`

**Expected Results:**
- Sub-menu remains
- Bot answers expense query in new message
- Free-form takes precedence (user is asking specific thing)

**Pass Criteria:**
- Both work, no menu state corruption

---

## TC-059: Open menu while wizard active

**Type:** Integration | **Story:** P3.6-S9 | **Persona:** Minh

**Steps:**
1. Start `/add_asset` wizard
2. Mid-wizard (e.g., asking subtype), send `/menu`
3. Observe behavior

**Expected Results:**
- Either:
  - **(a)** Bot says "Đang trong wizard, hủy không?" with confirm
  - **(b)** Menu opens, wizard state preserved (user can resume by responding)
- NOT acceptable: Wizard silently lost or menu errors

**Pass Criteria:**
- Either behavior acceptable
- Wizard not silently broken

---

## TC-060: Old menu callback — graceful redirect

**Type:** Migration | **Story:** P3.6-S9 | **Persona:** Hà

**Preconditions:**
- Hà has stale message from before deploy with old callback (e.g., menu_old:assets)

**Steps:**
1. Find old menu message in chat history (from before Phase 3.6 deploy)
2. Tap old button

**Expected Results:**
- Bot doesn't crash on unknown callback
- Sends graceful message: "Menu đã được nâng cấp! Mở /menu để xem giao diện mới"

**Pass Criteria:**
- No error
- User redirected to new menu

---

# Section 6 — Migration & Cutover

## TC-061: Pre-deploy announcement received

**Type:** Migration | **Story:** P3.6-S11 | **Persona:** All real users

**Preconditions:** Day before deploy, broadcast scheduled

**Steps:**
1. Verify all active users received announcement message
2. Check timing (1 day before deploy)

**Expected Results:**
- Message arrived
- Content matches spec:
  - Mentions 5 mảng
  - Tells user when (date + time)
  - Reassures features still there

**Pass Criteria:**
- All users notified
- Message clear and accurate

---

## TC-062: Deploy day — smoke test

**Type:** Migration | **Story:** P3.6-S11 | **Persona:** Test admin

**Preconditions:** Right after deploy

**Steps:**
1. Send `/menu` → verify new menu
2. Tap each of 5 categories → verify sub-menus load
3. Test 1 action per category (5 actions total)
4. Send free-form query → verify Phase 3.5 still works
5. Check error logs

**Expected Results:**
- All checks pass
- No errors in logs
- Response times normal

**Pass Criteria:**
- 100% of smoke test pass
- Deploy "green light"

---

## TC-063: Post-deploy notification received

**Type:** Migration | **Story:** P3.6-S11 | **Persona:** All real users

**Steps:**
1. Within 1 hour of deploy, verify users received notification
2. Check content

**Expected Results:**
- Message: "✨ Menu mới đã sẵn sàng!"
- Encourages /menu OR free-form
- Friendly tone

**Pass Criteria:**
- All users notified
- Message accurate

---

## TC-064: 4-hour monitoring — no critical errors

**Type:** Migration | **Story:** P3.6-S11 | **Persona:** Test admin

**Steps:**
1. Monitor error logs for 4 hours post-deploy
2. Track:
   - Error rate
   - User complaints
   - /menu invocation count
   - Critical flow breakages

**Expected Results:**
- Error rate <5%
- 0-2 user complaints (minor only)
- /menu invocations spike then normalize
- No critical flows broken

**Pass Criteria:**
- All monitoring metrics within thresholds
- No rollback needed

---

## TC-065: Rollback procedure — verified working

**Type:** Migration | **Story:** P3.6-S11 | **Persona:** Test admin

**Note:** This is a verification test, run in staging environment (not production)

**Steps:**
1. In staging, deploy new menu
2. Verify it works
3. Run rollback command
4. Verify old menu restored
5. Verify users not affected

**Expected Results:**
- Rollback completes in <5 minutes
- Old menu functional again after rollback
- No data loss

**Pass Criteria:**
- Rollback rehearsed and confirmed working
- Confidence to deploy production

---

# Section 7 — Corner & Negative Cases

## TC-066: Spam tap same button rapidly

**Type:** Corner | **Story:** P3.6-S4 | **Persona:** Hà

**Steps:**
1. Send `/menu`
2. Tap "💎 Tài sản" 5 times rapidly (within 2 seconds)

**Expected Results:**
- Bot doesn't crash
- Only 1 sub-menu shown (subsequent taps ignored OR refresh same)
- No duplicate messages

**Pass Criteria:**
- Stable behavior under rapid tap
- No errors

---

## TC-067: Tap button on very old menu (24h+)

**Type:** Corner | **Story:** P3.6-S4 | **Persona:** Hà

**Steps:**
1. Find old /menu message from 24+ hours ago in chat
2. Tap a button

**Expected Results:**
- Bot still handles callback OR sends graceful "Menu cũ rồi, mở /menu mới nhé"
- No crash

**Pass Criteria:**
- Graceful handling

---

## TC-068: Network interruption during navigation

**Type:** Corner | **Story:** P3.6-S4 | **Persona:** Hà

**Steps:**
1. /menu → tap 💎 Tài sản
2. Immediately disconnect network (airplane mode)
3. Wait 5 seconds
4. Reconnect
5. Observe

**Expected Results:**
- After reconnect, navigation either:
  - **(a)** Completes (Telegram queues request)
  - **(b)** Shows error, user can retry
- No partial state

**Pass Criteria:**
- Graceful network handling

---

## TC-069: Very long display_name

**Type:** Corner | **Story:** P3.6-S2 | **Persona:** Test user with name = "ABC " * 50 (200 chars)

**Steps:**
1. Set display_name to very long string
2. /menu

**Expected Results:**
- Bot truncates name OR handles gracefully
- Menu still readable
- No layout broken

**Pass Criteria:**
- No crash
- Menu still usable

---

## TC-070: User with special chars in display_name

**Type:** Corner | **Story:** P3.6-S2 | **Persona:** Test user "Hà_*[bold]*_"

**Steps:**
1. Set display_name with Markdown special chars
2. /menu

**Expected Results:**
- Markdown chars escaped properly OR plain text
- Title doesn't break formatting
- No `**` artifacts

**Pass Criteria:**
- Special chars handled
- No Markdown injection

---

## TC-071: Menu when user has 0 assets

**Type:** Corner | **Story:** P3.6-S5 | **Persona:** New user "Empty"

**Preconditions:** New user, no assets

**Steps:**
1. /menu → 💎 Tài sản → 📊 Tổng tài sản

**Expected Results:**
- Bot shows empty state: "Bạn chưa có tài sản nào, thêm 1 cái để bắt đầu!"
- Suggests next action (➕ Thêm tài sản)

**Pass Criteria:**
- Empty state graceful
- Helpful suggestion

---

## TC-072: Menu when wealth_level cannot be determined

**Type:** Corner | **Story:** P3.6-S7 | **Persona:** New user with `NULL` net worth

**Preconditions:** Edge case — net worth calculation fails or returns null

**Steps:**
1. /menu

**Expected Results:**
- Bot doesn't crash
- Falls back to default level (young_prof)
- Menu still functional

**Pass Criteria:**
- Graceful fallback for missing data

---

## TC-073: Sub-menu callback with malformed data

**Type:** Negative | **Story:** P3.6-S4 | **Persona:** Test admin

**Note:** Hard to manually trigger. Document expected behavior.

**Expected behavior:**
- Bot validates callback data format
- Unknown callbacks → graceful "Hành động không hợp lệ" message
- No exception exposed to user

**Manual test alternative:**
- Send all 23 actions across 1 hour
- Watch for any "internal error" exposed
- Should be 0

**Pass Criteria:**
- 0 exposed errors during sweep

---

## TC-074: Callback abuse — random malicious callback

**Type:** Negative | **Story:** P3.6-S4 | **Persona:** Adversarial test

**Steps:**
1. Use Telegram client/script to send arbitrary callback_data: `menu:hack:drop_table`
2. Observe response

**Expected Results:**
- Bot rejects unknown callback
- No SQL injection or crash
- Logged for security review

**Pass Criteria:**
- Robust against malformed callbacks
- No system damage

---

## TC-075: Mobile keyboard hides menu — usability

**Type:** Visual | **Story:** P3.6-S2 | **Persona:** Hà (on iPhone)

**Steps:**
1. /menu (full menu visible)
2. Tap text input area to open keyboard
3. Observe menu position

**Expected Results:**
- Menu scrolls up correctly when keyboard appears
- Buttons still tappable above keyboard
- No buttons hidden behind keyboard

**Pass Criteria:**
- Mobile keyboard interaction OK

---

# Section 8 — Regression Tests

## TC-076: /add_asset wizard — independent of menu

**Type:** Regression | **Story:** P3.6-S10 | **Persona:** Minh

**Steps:**
1. Send `/add_asset` directly (NOT through menu)
2. Complete wizard:
   - Tap "💵 Tiền mặt / TK"
   - Tap "🏦 Tiết kiệm ngân hàng"
   - Send: `Test Bank 1tr`
   - Confirm

**Expected Results:**
- Wizard works exactly as Phase 3A
- Asset created successfully

**Pass Criteria:**
- No regression in /add_asset

---

## TC-077: Storytelling mode — preserved

**Type:** Regression | **Story:** P3.6-S10 | **Persona:** Phương

**Preconditions:** Receive morning briefing

**Steps:**
1. Tap "💬 Kể chuyện" on briefing
2. Send: `hôm qua ăn nhà hàng 800k`
3. Confirm extracted transaction

**Expected Results:**
- Storytelling mode flows as Phase 3A
- Multi-transaction extract works
- Confirmation flow intact

**Pass Criteria:**
- Phase 3A storytelling not broken

---

## TC-078: Free-form intent queries — Phase 3.5 still works

**Type:** Regression | **Story:** P3.6-S10 | **Persona:** Phương

**Steps:**
1. Send 11 canonical Phase 3.5 queries:
   - "tài sản của tôi có gì?"
   - "chi tiêu tháng này"
   - "VNM giá bao nhiêu?"
   - "thu nhập của tôi"
   - "mục tiêu của tôi"
   - "portfolios chứng khoán"
   - ... (rest of 11)
2. Verify each returns correct response

**Expected Results:**
- All 11 queries answered correctly
- No degradation from Phase 3.5

**Pass Criteria:**
- 11/11 success rate

---

## TC-079: Voice queries — preserved

**Type:** Regression | **Story:** P3.6-S10 | **Persona:** Hà

**Steps:**
1. Send voice: "tài sản của tôi có gì"
2. Verify transcription + intent + response

**Expected Results:**
- Voice → text → intent → response works
- Same quality as Phase 3.5

**Pass Criteria:**
- Voice flow not broken

---

## TC-080: Morning briefing — 7 AM trigger

**Type:** Regression | **Story:** P3.6-S10 | **Persona:** Phương

**Preconditions:** Set briefing_time to 07:00

**Steps:**
1. Wait until next 7 AM (or simulate cron)
2. Verify briefing arrives
3. Verify content matches level (Mass Affluent template)

**Expected Results:**
- Briefing at 7:00 AM ± 15 min window
- Content as Phase 3A
- Inline keyboard present

**Pass Criteria:**
- Briefing system intact

---

# 📋 Test Execution Sheet Template

```
| TC ID | Title | Type | Status | Tester | Date | Notes |
|-------|-------|------|--------|--------|------|-------|
| TC-001 | /menu basic | Happy | _____ | _____ | _____ | _____ |
... 
```

**Status values:** ✅ PASS, ⚠️ PASS WITH NOTES, ❌ FAIL, 🚫 BLOCKED, ⏭ SKIPPED

---

# 🎯 Phase 3.6 Exit Criteria Verification

After all test cases, verify Phase 3.6 exit criteria:

| Criterion | How to Verify | TC References |
|-----------|---------------|---------------|
| /menu shows 5-category structure | Section 1 | TC-001 |
| 3-level navigation works | Section 2 | TC-011, TC-013 |
| All 23 actions handled | Section 3 | TC-037 |
| Adaptive intros across 4 levels | Section 4 | TC-045 (side-by-side) |
| Coexists with free-form queries | Section 5 | TC-056-058 |
| Hard cutover deploy successful | Section 6 | TC-061-064 |
| No regressions in existing flows | Section 8 | TC-076-080 |
| Old menu fully retired | Section 6 + cleanup story | TC-060 |

If all criteria met → ✅ Ship to all users.
If 1-2 failed → 🔄 Fix specific issues.
If 3+ failed → 🛑 Hold deploy, return to phase-3.6-detailed.md.

---

# 🐛 Common Failure Modes — What to Watch

## 1. Old Menu Still Visible
- Cause: Cache not invalidated, deploy incomplete
- Action: Force /menu, verify version in logs

## 2. Adaptive Intro Always Same
- Cause: wealth_level detection failing, defaulting
- Action: Check NetWorthCalculator works for the user

## 3. Edit-in-Place Not Working
- Cause: Bot sending new message instead of editing
- Action: Check `query.edit_message_text()` used (not `reply_text`)

## 4. Callback Errors
- Cause: Stale message with old callback format
- Action: Document for users; deploy graceful fallback

## 5. Wizard State Lost
- Cause: Menu opened mid-wizard cleared user_data
- Action: Document expected behavior, don't clear wizard state

## 6. Buttons Wrap on Mobile
- Cause: Label too long
- Action: Shorten label to ≤16 chars

## 7. Performance Degradation
- Cause: Wealth-level detection on every render
- Action: Add caching (5 min TTL)

---

# 📊 Test Coverage Summary

```
Total test cases: 80
By Section:
  S1 Main Menu Display:        10 cases (TC-001 to TC-010)
  S2 Sub-Menu Navigation:      10 cases (TC-011 to TC-020)
  S3 Action Triggering:        20 cases (TC-021 to TC-040)
  S4 Adaptive Intros:          15 cases (TC-041 to TC-055)
  S5 Free-form Coexistence:     5 cases (TC-056 to TC-060)
  S6 Migration & Cutover:       5 cases (TC-061 to TC-065)
  S7 Corner & Negative:        10 cases (TC-066 to TC-075)
  S8 Regression:                5 cases (TC-076 to TC-080)

By Type:
  Happy:        ~25 cases (31%)
  Visual:       ~15 cases (19%)
  Integration:  ~15 cases (19%)
  Corner:       ~10 cases (13%)
  Migration:     ~5 cases (6%)
  Regression:    ~5 cases (6%)
  Negative:      ~3 cases (4%)
  Performance:   ~2 cases (3%)
```

---

# 🚀 Final Notes for Tester

## Before Testing
1. Read `phase-3.6-detailed.md` to understand the menu structure
2. Read `phase-3.6-issues.md` for context per story
3. Verify 4 personas set up (reuse Phase 3.5 setup)
4. Have iPhone, Android, and Desktop Telegram ready
5. Stopwatch for performance tests

## During Testing
1. Test in order within Sections (deps may exist)
2. Take screenshots especially for Section 4 (adaptive)
3. Note exact text of failures
4. Capture both screen + logs (when accessible)

## After Testing
1. Compile execution sheet
2. Categorize failures by severity
3. Side-by-side compare 4-level intros (TC-045)
4. Submit detailed report
5. Sign off when exit criteria met

## Critical Tests Don't Skip
- TC-045: Side-by-side adaptive comparison (THE key UX test)
- TC-037: All 23 actions sweep (catches broken handlers)
- TC-064: 4-hour post-deploy monitoring (catches production issues)
- TC-076-080: Regression suite (protects existing functionality)

**Test thoroughly. Phase 3.6 is the visual face of Personal CFO positioning. 🎨💚**
