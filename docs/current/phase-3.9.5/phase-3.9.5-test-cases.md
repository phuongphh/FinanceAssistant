# Phase 3.9.5 — Manual Test Cases (Telegram Bot)

<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->

> **Purpose:** Comprehensive test cases for Phase 3.9.5 (Pre-Launch UX Polish).
> **Tester Profile:** No source code access. Tests via Telegram chat (premium + non-premium accounts).
> **Reference:** [phase-3.9.5-detailed.md](./phase-3.9.5-detailed.md), [phase-3.9.5-issues.md](./phase-3.9.5-issues.md)

---

## 📋 How to Use This Document

### Test Case Structure

```
TC-XXX: [Title]
Type: Happy | Corner | Regression | Integration | Performance | Critical
Story: P3.9.5-Sn (links to issue)
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

**Reuse 4 personas from Phase 3.7/3.8/3.8.5 + Phase 3.9 market data setup. 1 new persona for emoji testing.**

### Persona 1: Hà (Trẻ Năng Động, ~140tr)
- Account age: ~60 days
- Multiple income streams, 1 goal active, recurring patterns
- Portfolio: 5 cổ phiếu (VNM, FPT, HPG, MWG, VIC) + 3 crypto (BTC, ETH, SOL) + 2 chỉ vàng SJC
- Telegram: **non-premium** account
- Wealth level: Trẻ Năng Động 🚀

### Persona 2: Phương (Trung Lưu Vững, ~4.5 tỷ)
- Account age: ~90 days
- Rental property, multi-income, 2 goals
- Portfolio: 12 cổ phiếu, 5 crypto, 30 chỉ vàng, 1 BĐS cho thuê
- Telegram: **premium** account (test animation emojis)
- Wealth level: Tinh Hoa 🏆

### Persona 3: Anh Tùng (Tinh Hoa, ~13 tỷ)
- Account age: ~120 days
- HNW, complex portfolio
- Telegram: **premium** account
- Wealth level: Tinh Hoa 🏆

### Persona 4: Mai (Khởi Đầu, ~15tr)
- Account age: ~14 days
- Empty portfolio (0 stocks, 0 crypto, 0 gold)
- Telegram: **non-premium**
- Wealth level: Khởi Đầu 🌱
- Use for empty state testing

### Persona 5 (NEW): Test bot owner — Premium animation observer
- Premium Telegram subscriber
- Used cho TC Epic 5 verify emoji animation render

---

## 🗂️ Test Case Index

| Range | Epic / Topic |
|-------|--------------|
| TC-001 — TC-010 | Epic 1: Wealth Menu (S1, S2, S3) |
| TC-011 — TC-020 | Epic 2: Dashboard (S4, S5) |
| TC-021 — TC-040 | Epic 3: Cashflow Menu (S6-S10) |
| TC-041 — TC-060 | Epic 4: Market Menu (S11-S16) — includes P1 bug TC |
| TC-061 — TC-072 | Epic 5: Animation Emoji (S17-S19) |
| TC-073 — TC-080 | Cross-epic regression + edge cases |

**Total:** ~80 manual TC across 5 Epics + regression.

---

# Epic 1 — Wealth Menu (TC-001 → TC-010)

## TC-001: Tổng tài sản không còn câu "Đây là hình ảnh..."
- **Type:** Happy
- **Story:** P3.9.5-S1
- **Persona:** Hà
- **Preconditions:** User đã track ít nhất 1 asset
- **Steps:**
  1. Mở Telegram, click menu Tài sản
  2. Click "📊 Tổng tài sản"
- **Expected:**
  - View hiển thị net worth + breakdown asset types
  - **KHÔNG còn** câu mở đầu "Đây là hình ảnh..."
  - Layout sạch, intro ngắn gọn hoặc đi thẳng vào số liệu
- **Pass:** câu cũ vắng mặt, layout không bị vỡ

## TC-002: Tổng tài sản với empty portfolio
- **Type:** Corner
- **Story:** P3.9.5-S1
- **Persona:** Mai
- **Preconditions:** Mai chưa add asset nào
- **Steps:**
  1. Click menu Tài sản → Tổng tài sản
- **Expected:**
  - Empty state hiển thị friendly Bé Tiền tone
  - Không có câu "Đây là hình ảnh..."
  - Có CTA "Thêm tài sản đầu tiên"
- **Pass:** empty state ok, no leftover copy

## TC-003: Báo cáo chi tiết — không còn button "Phân bổ chi tiết"
- **Type:** Happy
- **Story:** P3.9.5-S2
- **Persona:** Phương
- **Preconditions:** Phương có portfolio đa dạng
- **Steps:**
  1. Menu Tài sản → "📈 Báo cáo chi tiết"
- **Expected:**
  - View báo cáo hiển thị bình thường
  - **KHÔNG còn** button "Phân bổ chi tiết"
  - Các button còn lại render đúng
- **Pass:** button bị xoá, không còn callback dead-end

## TC-004: YTD return — full year case (Phương 4.5 tỷ)
- **Type:** Happy
- **Story:** P3.9.5-S2
- **Persona:** Phương
- **Preconditions:** Phương có account > 1 năm + snapshot net worth tại 1/1/2026
- **Steps:**
  1. Menu Tài sản → Báo cáo chi tiết
  2. Click button "YTD return"
- **Expected:**
  - Hiển thị return % từ 1/1/2026 → today
  - Format: "+5.2%" hoặc "-3.1%" với emoji 📈/📉
  - Có giải thích: "Từ 1/1/2026 đến nay"
- **Pass:** số tính đúng, format đúng

## TC-005: YTD return — partial year case (Hà ~60 ngày)
- **Type:** Corner
- **Story:** P3.9.5-S2
- **Persona:** Hà
- **Preconditions:** Hà account < 1 năm (~60 ngày)
- **Steps:**
  1. Menu Tài sản → Báo cáo chi tiết → YTD return
- **Expected:**
  - Fallback message: "Từ ngày tham gia: +X%"
  - Không crash, không hiển thị YTD vì không đủ baseline
- **Pass:** fallback rõ ràng, không hiện "—" gây confuse

## TC-006: YTD return — zero base edge case
- **Type:** Corner
- **Story:** P3.9.5-S2
- **Persona:** Mai
- **Preconditions:** Mai có account, nhưng net worth = 0 tại 1/1
- **Steps:**
  1. Click YTD return
- **Expected:**
  - Display "—" hoặc "Chưa đủ data"
  - Không divide-by-zero error
- **Pass:** graceful handle

## TC-007: Xoá tài sản — chọn type trước
- **Type:** Happy
- **Story:** P3.9.5-S3
- **Persona:** Phương
- **Preconditions:** Phương có nhiều loại assets
- **Steps:**
  1. Menu Tài sản → tìm action "Xoá tài sản"
  2. Quan sát menu hiện ra
- **Expected:**
  - Menu chọn asset type trước (cổ phiếu / crypto / vàng / BĐS / cash / khác)
  - **KHÔNG** liệt kê tất cả assets ngay
- **Pass:** UX gating đúng pattern

## TC-008: Xoá tài sản — sau khi chọn Crypto, list filtered
- **Type:** Happy
- **Story:** P3.9.5-S3
- **Persona:** Phương
- **Steps:**
  1. Xoá tài sản → chọn "Crypto"
- **Expected:**
  - List chỉ hiển thị 5 coins của Phương (BTC, ETH, ...)
  - Mỗi row có button "🗑 Xoá" và confirmation step
  - Không lẫn cổ phiếu hay vàng
- **Pass:** filter đúng, no leak

## TC-009: Xoá tài sản — empty type
- **Type:** Corner
- **Story:** P3.9.5-S3
- **Persona:** Mai
- **Preconditions:** Mai chưa có crypto
- **Steps:**
  1. Xoá tài sản → chọn "Crypto"
- **Expected:**
  - Message "Không có tài sản loại này"
  - Button "Quay lại" hoặc tương tự
- **Pass:** empty state ok

## TC-010: Xoá tài sản — confirmation prevents accidental delete
- **Type:** Critical
- **Story:** P3.9.5-S3
- **Persona:** Hà
- **Steps:**
  1. Xoá tài sản → chọn Cổ phiếu → click 🗑 trên row VNM
  2. Quan sát confirmation
  3. Click "Huỷ"
- **Expected:**
  - Confirmation hiển thị tên + giá trị asset trước khi xoá
  - Click "Huỷ" → asset không bị xoá
  - Soft delete (deleted_at) — không hard delete
- **Pass:** confirmation hoạt động, asset preserved

---

# Epic 2 — Dashboard (TC-011 → TC-020)

## TC-011: Dashboard hiển thị "Báo cáo" thay vì "Báo cáo tài sản"
- **Type:** Happy
- **Story:** P3.9.5-S5
- **Persona:** Hà
- **Steps:**
  1. Mở Dashboard (qua command hoặc menu)
- **Expected:**
  - Header view hiển thị "📊 Báo cáo" (rút gọn)
  - **KHÔNG** còn "Báo cáo tài sản"
- **Pass:** rename applied đúng

## TC-012: Dashboard menu button rename
- **Type:** Happy
- **Story:** P3.9.5-S5
- **Persona:** any
- **Steps:**
  1. Quét tất cả menu xem button dẫn đến dashboard
- **Expected:**
  - Mọi button label "Báo cáo tài sản" đã đổi thành "Báo cáo"
- **Pass:** consistent rename

## TC-013: Click vào row asset trong dashboard → mở edit
- **Type:** Happy
- **Story:** P3.9.5-S4
- **Persona:** Phương
- **Preconditions:** Phương có ít nhất 5 assets multi-type
- **Steps:**
  1. Mở Dashboard → "📊 Báo cáo"
  2. Click vào 1 dòng cụ thể (e.g. dòng "VNM - 100 cổ")
- **Expected:**
  - Mở edit wizard cho VNM (existing asset_entry edit flow)
  - Form pre-filled với data hiện tại của VNM
  - Sau khi save → quay về Dashboard với data refreshed
- **Pass:** edit flow đúng asset, refresh ok

## TC-014: Dashboard — click row của group multi-instance
- **Type:** Corner
- **Story:** P3.9.5-S4
- **Persona:** Phương
- **Preconditions:** Phương có nhiều cổ phiếu (12+)
- **Steps:**
  1. Dashboard → click dòng "Cổ phiếu" (group level, nếu UI hiển thị grouped)
- **Expected:**
  - Hiển thị list các cổ phiếu để chọn 1 cụ thể
  - Click 1 cổ phiếu → mở edit wizard cho nó
- **Pass:** group→list→edit flow ok

## TC-015: Dashboard — edit cancel quay về dashboard không đổi data
- **Type:** Corner
- **Story:** P3.9.5-S4
- **Persona:** Phương
- **Steps:**
  1. Click row → mở edit
  2. Click "Huỷ" trong edit wizard
- **Expected:**
  - Quay về Dashboard
  - Data không thay đổi
  - No partial save
- **Pass:** cancel hoạt động đúng

## TC-016: Dashboard với empty portfolio
- **Type:** Corner
- **Story:** P3.9.5-S4
- **Persona:** Mai
- **Preconditions:** Mai chưa có asset
- **Steps:**
  1. Mở Dashboard
- **Expected:**
  - Empty state friendly
  - Không có rows → không có click-to-edit
  - CTA "Thêm tài sản"
- **Pass:** empty state graceful

## TC-017: Dashboard — layer contract compliance
- **Type:** Integration
- **Story:** P3.9.5-S4
- **Persona:** any (dev verification)
- **Steps:**
  1. Inspect callback handler chain khi click row
- **Expected:**
  - Handler call asset_service, không direct DB
  - Service không call db.commit (worker boundary)
  - layer-contract-checker pass
- **Pass:** contract clean

## TC-018: Dashboard — refresh sau edit reflects new value
- **Type:** Integration
- **Story:** P3.9.5-S4
- **Persona:** Hà
- **Steps:**
  1. Dashboard → click VNM (giá hiện tại 100tr)
  2. Edit qty từ 100 → 200 cổ
  3. Save
- **Expected:**
  - Quay về Dashboard
  - VNM hiển thị 200 cổ + total value updated
  - Net worth header updated
- **Pass:** end-to-end refresh hoạt động

## TC-019: Dashboard performance render < 2s
- **Type:** Performance
- **Story:** P3.9.5-S4 (incidental)
- **Persona:** Phương (large portfolio)
- **Steps:**
  1. Mở Dashboard (cold cache)
  2. Đo time đến khi message hiển thị đầy đủ
- **Expected:**
  - p95 < 2s với cached market data
  - p95 < 4s với cold cache
- **Pass:** within target

## TC-020: Dashboard regression — existing functionality intact
- **Type:** Regression
- **Story:** P3.9.5-S4, S5
- **Persona:** any
- **Steps:**
  1. Mở Dashboard, scroll qua các sections
  2. Click vào nav buttons existing (nếu có)
- **Expected:**
  - Tất cả sections render như trước (group breakdown, totals, charts)
  - Click row mới feature additive, không break existing nav
- **Pass:** zero regression

---

# Epic 3 — Cashflow Menu (TC-021 → TC-040)

## TC-021: Cashflow Tổng quan — label rõ ràng
- **Type:** Happy
- **Story:** P3.9.5-S6
- **Persona:** Hà
- **Preconditions:** Hà có thu/chi trong tháng
- **Steps:**
  1. Menu Dòng tiền → "📊 Tổng quan"
- **Expected:**
  - Label đầu trang rõ scope (e.g. "Dòng tiền tháng này" hoặc "30 ngày qua")
  - **KHÔNG** còn câu mơ hồ "Dòng tiền hiện tại của từng tháng"
- **Pass:** label hiểu được ngay

## TC-022: Cashflow Tổng quan — Bé Tiền tone
- **Type:** Happy
- **Story:** P3.9.5-S6
- **Persona:** Hà
- **Steps:**
  1. Menu Dòng tiền → Tổng quan
- **Expected:**
  - Intro câu warm, không robotic
  - Tone consistent với Phase 3.6/3.8.5
- **Pass:** đọc lên không cringy

## TC-023: Cashflow Tổng quan — không còn duplicate metric
- **Type:** Happy
- **Story:** P3.9.5-S7
- **Persona:** Phương
- **Steps:**
  1. Menu Dòng tiền → Tổng quan
  2. Đếm số lần "tỷ lệ tiết kiệm" xuất hiện
  3. Đếm số lần "Thu vs Chi" hoặc tương đương xuất hiện
- **Expected:**
  - Mỗi metric chỉ xuất hiện 1 lần
  - Card "So sánh tháng trước" không còn trùng lặp
- **Pass:** zero duplicate

## TC-024: Cashflow Tổng quan — 2 cards Thu / Chi tách biệt
- **Type:** Happy
- **Story:** P3.9.5-S8
- **Persona:** Phương
- **Steps:**
  1. Menu Dòng tiền → Tổng quan
- **Expected:**
  - Card riêng "💼 Thu nhập tháng" với total + top 2-3 sources + delta
  - Card riêng "💸 Chi tiêu tháng" với total + top 2-3 categories + delta
  - 2 cards layout consistent với nhau
- **Pass:** tách biệt rõ ràng

## TC-025: Card Thu nhập — top sources đúng
- **Type:** Happy
- **Story:** P3.9.5-S8
- **Persona:** Phương (multi-income)
- **Preconditions:** Phương có 3+ income streams
- **Steps:**
  1. Tổng quan → quan sát card Thu nhập
- **Expected:**
  - Top 3 sources ranked by amount tháng này
  - Format money: "45tr", "12tr", "5tr"
  - Delta vs tháng trước: "+10%" hoặc "-5%"
- **Pass:** ranking + format đúng

## TC-026: Card Chi tiêu — top categories đúng
- **Type:** Happy
- **Story:** P3.9.5-S8
- **Persona:** Hà
- **Steps:**
  1. Tổng quan → quan sát card Chi tiêu
- **Expected:**
  - Top 3 categories ranked
  - Money format short
  - Delta vs tháng trước
- **Pass:** ranking + format đúng

## TC-027: Card Thu / Chi với empty data
- **Type:** Corner
- **Story:** P3.9.5-S8
- **Persona:** Mai
- **Preconditions:** Mai chưa log thu/chi
- **Steps:**
  1. Tổng quan
- **Expected:**
  - Mỗi card có empty state riêng ("Chưa có thu nhập tháng này", CTA add)
  - Không crash
- **Pass:** empty state per card

## TC-028: Cashflow money formatting compliance
- **Type:** Integration
- **Story:** P3.9.5-S8 (incidental)
- **Persona:** Phương
- **Steps:**
  1. Quan sát mọi số tiền trong Cashflow view
- **Expected:**
  - Dùng `format_money_short` (45k, 1.2tr, 4.5 tỷ)
  - Decimal preservation, không float
- **Pass:** format consistent với CLAUDE.md rule

## TC-029: Button "📅 Dòng tiền tháng này" xuất hiện
- **Type:** Happy
- **Story:** P3.9.5-S9
- **Persona:** any
- **Steps:**
  1. Menu Dòng tiền
- **Expected:**
  - Submenu có button mới "📅 Dòng tiền tháng này"
  - Distinct với "📊 Tổng quan"
- **Pass:** button visible

## TC-030: Báo cáo "Dòng tiền tháng này" — content đầy đủ
- **Type:** Happy
- **Story:** P3.9.5-S9
- **Persona:** Phương
- **Steps:**
  1. Menu Dòng tiền → "📅 Dòng tiền tháng này"
- **Expected:**
  - Tổng thu / tổng chi / net flow tháng hiện tại
  - Thu nhập theo source (top 3)
  - Chi tiêu theo category (top 3)
  - Daily flow text-chart (best/worst day)
  - Top 3 biggest transactions
- **Pass:** content đầy đủ 5 sections

## TC-031: Báo cáo "Dòng tiền tháng này" — empty case
- **Type:** Corner
- **Story:** P3.9.5-S9
- **Persona:** Mai
- **Steps:**
  1. Click "📅 Dòng tiền tháng này"
- **Expected:**
  - Empty state friendly
  - Bé Tiền tone, suggest add transaction
- **Pass:** graceful empty

## TC-032: Báo cáo "Dòng tiền tháng này" — performance
- **Type:** Performance
- **Story:** P3.9.5-S9
- **Persona:** Phương
- **Steps:**
  1. Click button, đo time đến khi render
- **Expected:**
  - p95 < 2s
- **Pass:** within target

## TC-033: Báo cáo "Dòng tiền tháng này" — first vs middle of month
- **Type:** Corner
- **Story:** P3.9.5-S9
- **Persona:** Hà
- **Steps:**
  1. Click vào ngày 1 tháng (ít data)
  2. Click vào ngày 25 tháng (nhiều data)
- **Expected:**
  - Both render đúng, không crash
  - Ngày 1 hiển thị "Mới đầu tháng, data ít"
  - Ngày 25 hiển thị full breakdown
- **Pass:** time-of-month aware

## TC-034: Button "🎯 Mục tiêu" trong Cashflow xuất hiện
- **Type:** Happy
- **Story:** P3.9.5-S10
- **Persona:** any
- **Steps:**
  1. Menu Dòng tiền
- **Expected:**
  - Submenu có button mới "🎯 Mục tiêu"
- **Pass:** button visible

## TC-035: Cashflow → Mục tiêu → redirect Goals existing
- **Type:** Integration
- **Story:** P3.9.5-S10
- **Persona:** Phương (có 2 goals)
- **Steps:**
  1. Menu Dòng tiền → "🎯 Mục tiêu"
- **Expected:**
  - Render goals list existing (giống menu Goals)
  - Phương thấy 2 goals của mình
  - Không tạo Goals layer khác
- **Pass:** redirect đúng

## TC-036: Cashflow → Mục tiêu → back button quay về Cashflow
- **Type:** Integration
- **Story:** P3.9.5-S10
- **Persona:** Phương
- **Steps:**
  1. Cashflow → Mục tiêu → back
- **Expected:**
  - Quay về submenu Cashflow (không phải submenu Goals)
- **Pass:** back context giữ đúng

## TC-037: Cashflow → Mục tiêu — empty goals
- **Type:** Corner
- **Story:** P3.9.5-S10
- **Persona:** Mai (chưa có goal)
- **Steps:**
  1. Cashflow → Mục tiêu
- **Expected:**
  - Empty state Goals + CTA "Tạo mục tiêu đầu tiên"
- **Pass:** empty state ok

## TC-038: Cashflow regression — Tổng quan vẫn render
- **Type:** Regression
- **Story:** P3.9.5-S6, S7, S8
- **Persona:** Hà
- **Steps:**
  1. Menu Dòng tiền → Tổng quan
- **Expected:**
  - View render thành công, không bị broken sau restructure
  - Tỷ lệ tiết kiệm vẫn correct
  - Thu vs Chi card vẫn correct
- **Pass:** zero regression

## TC-039: Cashflow regression — voice query "thu chi tháng này"
- **Type:** Regression
- **Story:** P3.9.5-S6 (intent layer)
- **Persona:** Hà
- **Steps:**
  1. Voice query "thu chi tháng này"
- **Expected:**
  - Intent classified correctly QUERY_CASHFLOW
  - Response render new layout
- **Pass:** voice intent vẫn hoạt động

## TC-040: Cashflow vi-localization-checker pass
- **Type:** Integration
- **Story:** P3.9.5-S6, S7, S8, S9, S10
- **Persona:** dev
- **Steps:**
  1. Run `vi-localization-checker` agent on changes
- **Expected:**
  - No hardcoded Vietnamese strings introduced
  - All copy in `content/menu_copy.yaml`
  - Bé Tiền tone consistent
- **Pass:** checker clean

---

# Epic 4 — Market Menu (TC-041 → TC-060)

## TC-041: 🚨 P1 BUG — Crypto Portfolios không nhảy sang Stocks
- **Type:** Critical
- **Story:** P3.9.5-S13
- **Persona:** Hà (3 crypto coins)
- **Preconditions:** Hà có cả stocks lẫn crypto trong portfolio
- **Steps:**
  1. Menu Thị trường → "₿ Tiền số"
  2. Click "Portfolios của tôi"
- **Expected:**
  - Hiển thị **3 coins của Hà** (BTC, ETH, SOL)
  - **KHÔNG** hiển thị stocks (VNM, FPT...)
  - Header rõ "Crypto Portfolio"
- **Pass:** routing đúng asset_type=crypto

## TC-042: P1 BUG regression — Stocks Portfolios vẫn đúng
- **Type:** Regression
- **Story:** P3.9.5-S13
- **Persona:** Hà
- **Steps:**
  1. Menu Thị trường → "📈 Cổ phiếu"
  2. Click "Portfolios của tôi"
- **Expected:**
  - Hiển thị 5 cổ phiếu của Hà
  - Không lẫn crypto
- **Pass:** stocks routing không bị break

## TC-043: P1 BUG audit — Vàng Portfolios cùng pattern
- **Type:** Critical
- **Story:** P3.9.5-S13
- **Persona:** Phương (30 chỉ vàng)
- **Steps:**
  1. Menu Thị trường → "🥇 Vàng" (renamed)
  2. Click "Portfolios của tôi"
- **Expected:**
  - Hiển thị vàng holdings
  - **KHÔNG** lẫn stocks/crypto
- **Pass:** Vàng không cùng bug

## TC-044: Tiền số performance — cached p95 < 2s
- **Type:** Performance
- **Story:** P3.9.5-S12
- **Persona:** Hà
- **Preconditions:** Cache warm (đã fetch trong 120s qua)
- **Steps:**
  1. Menu Thị trường → Tiền số
  2. Đo time message render
  3. Repeat 10 lần, lấy p95
- **Expected:**
  - p95 < 2s
- **Pass:** within target

## TC-045: Tiền số performance — cold cache p95 < 4s
- **Type:** Performance
- **Story:** P3.9.5-S12
- **Persona:** Hà
- **Preconditions:** Flush Redis cache crypto
- **Steps:**
  1. Click Tiền số (cold)
  2. Đo time
- **Expected:**
  - p95 < 4s
- **Pass:** cold case acceptable

## TC-046: Tiền số stale-data fallback
- **Type:** Corner
- **Story:** P3.9.5-S12
- **Persona:** Hà
- **Preconditions:** CoinGecko mock down (provider unavailable)
- **Steps:**
  1. Click Tiền số
- **Expected:**
  - Hiển thị giá last_known
  - Banner "⚠️ Dữ liệu cập nhật lần cuối: HH:mm"
  - Không crash, không 500 error
- **Pass:** fallback hoạt động

## TC-047: Tiền số batch fetch khi portfolio nhiều coin
- **Type:** Performance
- **Story:** P3.9.5-S12
- **Persona:** Phương (5 crypto coins)
- **Steps:**
  1. Click Tiền số
  2. Inspect network calls (dev mode)
- **Expected:**
  - Single batch call (không phải 5 calls riêng lẻ)
  - p95 < 2s với cached
- **Pass:** batching hoạt động

## TC-048: Cổ phiếu — Bảng giá filter theo portfolio
- **Type:** Happy
- **Story:** P3.9.5-S11
- **Persona:** Hà (5 stocks)
- **Steps:**
  1. Menu Thị trường → Cổ phiếu → "Bảng giá"
- **Expected:**
  - Chỉ hiển thị 5 mã của Hà
  - Không show all VN30
- **Pass:** filter đúng

## TC-049: Cổ phiếu — Bảng giá empty portfolio
- **Type:** Corner
- **Story:** P3.9.5-S11
- **Persona:** Mai (no stocks)
- **Steps:**
  1. Cổ phiếu → Bảng giá
- **Expected:**
  - Empty state với hint "Thêm CK vào portfolio để theo dõi"
  - CTA add stock
- **Pass:** empty state ok

## TC-050: Cổ phiếu — Tìm CK theo mã
- **Type:** Happy
- **Story:** P3.9.5-S11
- **Persona:** any
- **Steps:**
  1. Cổ phiếu → "🔍 Tìm CK theo mã"
  2. Gõ "VNM"
- **Expected:**
  - Hiển thị quote VNM (giá, change, volume)
  - Source SSI
- **Pass:** query path hoạt động

## TC-051: Cổ phiếu — Tìm CK invalid ticker
- **Type:** Corner
- **Story:** P3.9.5-S11
- **Persona:** any
- **Steps:**
  1. Tìm CK theo mã → gõ "XYZZZZ"
- **Expected:**
  - Friendly error "Không tìm thấy mã XYZZZZ. Bạn check lại nhé."
  - Không crash
- **Pass:** error handle

## TC-052: Cổ phiếu — Tìm CK 5-phút cache
- **Type:** Performance
- **Story:** P3.9.5-S11
- **Persona:** any
- **Steps:**
  1. Tìm "VNM" → ghi nhận giá
  2. Tìm "VNM" lại trong 5 phút
- **Expected:**
  - Lần 2 nhanh hơn (cache hit)
  - Giá giống lần 1 (cùng cache)
- **Pass:** cache TTL hoạt động

## TC-053: Button "Sửa tài sản" trong Crypto Portfolios
- **Type:** Happy
- **Story:** P3.9.5-S14
- **Persona:** Hà
- **Steps:**
  1. Tiền số → Portfolios của tôi
- **Expected:**
  - Có button "✏️ Sửa tài sản" trong view
  - Click → list 3 coins của Hà (filtered crypto only)
  - Edit 1 coin → save → quay về Crypto Portfolios
- **Pass:** filtered edit + return context

## TC-054: Button "Sửa tài sản" trong Stocks Portfolios
- **Type:** Happy
- **Story:** P3.9.5-S14
- **Persona:** Hà
- **Steps:**
  1. Cổ phiếu → Portfolios của tôi → Sửa tài sản
- **Expected:**
  - List filtered chỉ stocks
  - Quay về Stocks Portfolios sau edit
- **Pass:** consistent pattern

## TC-055: Button "Sửa tài sản" trong Vàng Portfolios
- **Type:** Happy
- **Story:** P3.9.5-S14
- **Persona:** Phương
- **Steps:**
  1. Vàng → Portfolios của tôi → Sửa tài sản
- **Expected:**
  - List filtered chỉ vàng
  - Quay về Vàng Portfolios sau edit
- **Pass:** consistent

## TC-056: Button "Sửa tài sản" empty state
- **Type:** Corner
- **Story:** P3.9.5-S14
- **Persona:** Mai (no crypto)
- **Steps:**
  1. Tiền số → Portfolios → Sửa tài sản
- **Expected:**
  - Empty state "Chưa có tài sản loại này"
  - CTA "Thêm crypto đầu tiên"
- **Pass:** empty state per type

## TC-057: Vàng → Portfolios có hint UX
- **Type:** Happy
- **Story:** P3.9.5-S15
- **Persona:** Phương
- **Steps:**
  1. Vàng → Portfolios của tôi
- **Expected:**
  - Hint string xuất hiện: "Đây là toàn bộ vàng bạn đang nắm giữ, định giá theo SJC realtime" (hoặc tương đương)
  - Hint vắng trong empty state nếu redundant
- **Pass:** hint visible

## TC-058: Stocks/Crypto Portfolios cũng có hint consistent
- **Type:** Happy
- **Story:** P3.9.5-S15
- **Persona:** Hà
- **Steps:**
  1. Quan sát hint ở Cổ phiếu Portfolios + Crypto Portfolios
- **Expected:**
  - 3 portfolios (stocks/crypto/gold) có hint pattern consistent
  - Mỗi hint phù hợp với asset type
- **Pass:** consistency

## TC-059: Rename "Vàng JSC" → "Vàng" trong submenu Market
- **Type:** Happy
- **Story:** P3.9.5-S16
- **Persona:** any
- **Steps:**
  1. Menu Thị trường
- **Expected:**
  - Button hiển thị "🥇 Vàng" (KHÔNG phải "Vàng JSC")
  - Bên trong view có thể clarify "Giá theo SJC" trong intro/footer
- **Pass:** rename applied

## TC-060: Market regression — VNINDEX, advisor flow vẫn hoạt động
- **Type:** Regression
- **Story:** P3.9.5-S11-S16
- **Persona:** Hà
- **Steps:**
  1. Menu Thị trường → VN-Index
  2. Menu Thị trường → "💡 Cơ hội đầu tư"
- **Expected:**
  - Cả 2 flows render đúng như trước
  - Không break sau routing/perf changes
- **Pass:** zero regression

---

