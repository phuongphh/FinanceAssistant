# Phase 3.9.5 — GitHub Issues

> **Reference:** [phase-3.9.5-detailed.md](./phase-3.9.5-detailed.md)
> **Structure:** Epic-as-parent / Story-as-child (consistent với Phase 3.5, 3.7, 3.8.5, 3.9)
> **Total:** 5 Epics, 19 Stories, ~5-7 ngày work
> **Labels:** `phase-3.9.5`, `ux-polish`, plus per-Epic labels

---

## Phase Overview

Phase 3.9.5 là pre-launch UX polish phase chèn giữa Phase 3.9 và Phase 4A. Mục tiêu: khắc phục 11 dogfooding findings + 2 menu rename + upgrade Telegram animation emojis, để soft launch tháng 6/2026 chạy trên foundation sạch và Twin (Phase 4A) build lên trên không kế thừa bug.

**Critical path:** Epic 4 (bugs + perf, highest priority) → Epic 1 + Epic 2 (independent, low risk, parallelizable) → Epic 3 (largest scope, 5 stories) → Epic 5 (cross-cut emoji, làm cuối).

---

# Epic 1: Tài sản (Wealth Menu Polish)

**Label:** `epic`, `phase-3.9.5`, `wealth`
**Estimate:** 1 ngày (~Day 3)
**Goal:** Loại bỏ UX debt trong submenu Tài sản — xoá copy thừa, fix logic button, gating cho destructive action.

**Stories:** S1, S2, S3

---

## [Story] P3.9.5-S1: Xoá câu "Đây là hình ảnh..." trong Tổng tài sản

**Labels:** `story`, `phase-3.9.5`, `wealth`, `copy`
**Parent:** Epic 1
**Estimate:** 0.25 ngày

### Description
Câu "Đây là hình ảnh..." dài, redundant với context, làm rối view "Tổng tài sản". Xoá hoặc thay bằng empty.

### Acceptance Criteria
- [ ] Identify exact YAML key chứa câu (likely `content/menu_copy.yaml` → `action_assets_net_worth`)
- [ ] Xoá câu (hoặc thay bằng empty string nếu key vẫn được referenced)
- [ ] Render view "Tổng tài sản" không còn câu này
- [ ] vi-localization-checker pass
- [ ] No code references broken

### Technical Notes
- Pure content YAML change, no handler change
- Verify key không bị hardcoded fallback trong code

### Dependencies
None.

---

## [Story] P3.9.5-S2: Bỏ button "Phân bổ chi tiết" + sửa logic YTD return

**Labels:** `story`, `phase-3.9.5`, `wealth`, `bug`
**Parent:** Epic 1
**Estimate:** 0.5 ngày

### Description
Button "Phân bổ chi tiết" trùng chức năng với view khác → xoá. Button "YTD return" hiện logic sai — cần fix tính từ 1/1/year.

### Acceptance Criteria
- [ ] Button "Phân bổ chi tiết" bị xoá khỏi menu báo cáo chi tiết tài sản
- [ ] YTD return computed đúng: từ 1/1/current_year → today, base = net worth tại 1/1, return = (current - base) / base * 100%
- [ ] Edge case: account < 1 năm → fallback message "Từ ngày tham gia: X%"
- [ ] Edge case: zero base → display "—" thay vì divide-by-zero
- [ ] Unit test cho YTD calc với 3 cases: full year, partial year, zero base
- [ ] Display format: "+5.2%" or "-3.1%" với màu emoji (📈/📉)

### Technical Notes
- File: `backend/services/wealth_dashboard_service.py` hoặc tương đương
- Cần snapshot net_worth tại 1/1/year — check nếu có existing snapshot table

### Dependencies
None.

---

## [Story] P3.9.5-S3: Flow xoá tài sản — chọn type trước

**Labels:** `story`, `phase-3.9.5`, `wealth`, `ux`
**Parent:** Epic 1
**Estimate:** 0.5 ngày

### Description
Hiện tại "Xoá tài sản" liệt kê hết tất cả → quá dài. Pattern mới: chọn asset type trước → list filtered.

### Acceptance Criteria
- [ ] User click "Xoá tài sản" → menu chọn asset type (cổ phiếu / crypto / vàng / BĐS / cash / khác)
- [ ] Sau khi chọn type → list filtered chỉ assets của type đó
- [ ] Mỗi row có button "🗑 Xoá" với confirmation step
- [ ] Empty type → message "Không có tài sản loại này. [Quay lại]"
- [ ] Reuse type filter logic shared với S14 (button Sửa tài sản)
- [ ] No hard delete — soft delete via `deleted_at` (CLAUDE.md rule)

### Technical Notes
- File: `backend/bot/handlers/asset_entry.py`
- Refactor existing list view nếu cần để reuse logic

### Dependencies
None. (S14 sẽ depend on shared filter helper from this Story.)

---

# Epic 2: Dashboard

**Label:** `epic`, `phase-3.9.5`, `dashboard`
**Estimate:** 0.75 ngày (~Day 4 morning)
**Goal:** Dashboard từ static report → interactive (click-to-edit), rename ngắn gọn.

**Stories:** S4, S5

---

## [Story] P3.9.5-S4: Click vào dòng tài sản → mở edit flow

**Labels:** `story`, `phase-3.9.5`, `dashboard`, `ux`
**Parent:** Epic 2
**Estimate:** 0.5 ngày

### Description
Dashboard "Báo cáo tài sản" hiện liệt kê assets theo group nhưng không actionable. Cho phép click row → mở edit wizard.

### Acceptance Criteria
- [ ] Mỗi row asset trong dashboard có inline button hoặc callback `dashboard:edit:<asset_id>`
- [ ] Click → mở edit wizard của `asset_entry.py` cho asset đó (reuse existing flow)
- [ ] Nếu row đại diện 1 group (multiple instances cùng category) → show list để chọn 1 asset cụ thể
- [ ] Edit thành công → quay về dashboard với data refreshed
- [ ] Layer contract: handler call asset_service.update, không direct DB write
- [ ] Service NEVER calls db.commit (worker boundary commits)

### Technical Notes
- Files: `backend/services/wealth_dashboard_service.py` (add asset_id to serialization), `backend/bot/formatters/dashboard_formatter.py` (render inline buttons), `backend/bot/handlers/asset_entry.py` (new entry point từ dashboard callback)
- Callback data format: `dashboard:edit:<uuid>` — reuse existing edit wizard

### Dependencies
None.

---

## [Story] P3.9.5-S5: Rename "Báo cáo tài sản" → "Báo cáo"

**Labels:** `story`, `phase-3.9.5`, `dashboard`, `copy`
**Parent:** Epic 2
**Estimate:** 0.25 ngày

### Description
Title "Báo cáo tài sản" quá dài, "tài sản" đã rõ qua context → rút gọn.

### Acceptance Criteria
- [ ] Tất cả instance "Báo cáo tài sản" trong `content/menu_copy.yaml` → "Báo cáo"
- [ ] Header dashboard view hiển thị "📊 Báo cáo"
- [ ] Search test snapshots cho "Báo cáo tài sản" và update
- [ ] No code references broken

### Technical Notes
- Pure content YAML + test snapshot update

### Dependencies
None.

---

# Epic 3: Dòng tiền (Cashflow Menu)

**Label:** `epic`, `phase-3.9.5`, `cashflow`
**Estimate:** 1.5-2 ngày (~Day 4 afternoon - Day 5)
**Goal:** Restructure Tổng quan để rõ ràng hơn, dedupe cards trùng, tách Thu/Chi, add monthly report, add Goals link.

**Stories:** S6, S7, S8, S9, S10

---

## [Story] P3.9.5-S6: Sửa label "Dòng tiền hiện tại của từng tháng"

**Labels:** `story`, `phase-3.9.5`, `cashflow`, `copy`
**Parent:** Epic 3
**Estimate:** 0.25 ngày

### Description
Label hiện tại không rõ user đang xem gì. Cần wording chính xác hơn.

### Acceptance Criteria
- [ ] Label rõ: "Dòng tiền tháng này" hoặc "Tình hình dòng tiền 30 ngày qua"
- [ ] Câu intro của Tổng quan submenu reflect đúng scope (current month + so sánh nếu giữ)
- [ ] vi-localization-checker pass
- [ ] Bé Tiền tone consistent (warm, not robotic)

### Technical Notes
- File: `content/menu_copy.yaml` → `submenu_cashflow.intro` hoặc card titles

### Dependencies
None. Coordinate với S7 (cùng nằm trong Tổng quan view).

---

## [Story] P3.9.5-S7: Dedupe — bỏ "So sánh tháng trước" trùng

**Labels:** `story`, `phase-3.9.5`, `cashflow`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
Card "So sánh với tháng trước" overlap với "Thu vs Chi" và "Tỷ lệ tiết kiệm" — cùng số liệu, redundant.

### Acceptance Criteria
- [ ] Identify exact card đang hiển thị duplicate metrics → ghi nhận trong PR description
- [ ] Bỏ phần trùng (giữ "Thu vs Chi" + "Tỷ lệ tiết kiệm" làm canonical)
- [ ] Hoặc consolidate thành 1 card duy nhất với delta inline
- [ ] User test: xem report Tổng quan, mỗi metric chỉ xuất hiện 1 lần
- [ ] Không break test snapshots khác

### Technical Notes
- File: `backend/intent/handlers/query_cashflow.py`
- Có thể cần cập nhật service `cashflow_*` để bỏ output thừa

### Dependencies
S6 (cùng touch Tổng quan view).

---

## [Story] P3.9.5-S8: Tách riêng card Thu nhập / Chi tiêu

**Labels:** `story`, `phase-3.9.5`, `cashflow`, `ux`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
Hiện tại Thu nhập và Chi tiêu hiển thị chung 1 block → khó scan. Tách thành 2 cards độc lập.

### Acceptance Criteria
- [ ] Tổng quan có 2 cards độc lập: "💼 Thu nhập tháng" + "💸 Chi tiêu tháng"
- [ ] Mỗi card show: total + top 2-3 sources/categories + delta vs tháng trước
- [ ] Layout consistent với cards khác (header + total + breakdown)
- [ ] Money formatting via `currency_utils.format_money_short`
- [ ] Empty state riêng cho mỗi card

### Technical Notes
- Files: `backend/intent/handlers/query_cashflow.py`, `backend/bot/formatters/cashflow_formatter.py` (or inline in handler)

### Dependencies
S7 (clean structure trước khi tách).

---

## [Story] P3.9.5-S9: Thêm báo cáo "Dòng tiền tháng này"

**Labels:** `story`, `phase-3.9.5`, `cashflow`, `feature`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
User muốn 1 báo cáo deep-dive cho tháng hiện tại (không phải Tổng quan compare nhiều tháng).

### Acceptance Criteria
- [ ] Button mới "📅 Dòng tiền tháng này" trong submenu Cashflow
- [ ] Action key `("cashflow", "monthly_report")` → `IntentType.QUERY_CASHFLOW` với `focus: "current_month_detail"`
- [ ] Report content:
  - Tổng thu / tổng chi / net flow
  - Thu nhập theo source (top 3)
  - Chi tiêu theo category (top 3)
  - Daily flow text-chart (best/worst day)
  - Biggest 3 transactions
- [ ] Vietnamese copy through `content/menu_copy.yaml`
- [ ] Render trong < 2s

### Technical Notes
- Files: `content/menu_copy.yaml` (button), `backend/bot/handlers/menu_handler.py` (action routing), `backend/intent/handlers/query_cashflow.py` (sub-handler)

### Dependencies
S6, S7 (cùng cấu trúc Cashflow menu).

---

## [Story] P3.9.5-S10: Thêm "Mục tiêu" link tới existing Goals

**Labels:** `story`, `phase-3.9.5`, `cashflow`, `routing`
**Parent:** Epic 3
**Estimate:** 0.25 ngày

### Description
User muốn truy cập Goals từ Cashflow context — tiết kiệm và goals liên quan trực tiếp.

### Acceptance Criteria
- [ ] Button mới "🎯 Mục tiêu" trong submenu Cashflow
- [ ] Click → redirect sang submenu Goals existing (không tạo Goals layer mới)
- [ ] Action `("cashflow", "goals")` → dispatch tới `("goals", "list")` handler
- [ ] Test: từ Cashflow click Mục tiêu → goals list render đúng
- [ ] Back button quay lại submenu Cashflow

### Technical Notes
- Pure routing change in `menu_handler.py`
- No new handler needed

### Dependencies
None. Pre-existing Goals system from Phase 3.8.

---

# Epic 4: Thị trường (Market Menu)

**Label:** `epic`, `phase-3.9.5`, `market`
**Estimate:** 2 ngày (~Day 1-2)
**Goal:** Fix Crypto routing bug, perf < 2s, chuẩn hoá Portfolios pattern, rename, hint UX. **Highest priority Epic.**

**Stories:** S11, S12, S13, S14, S15, S16

---

## [Story] P3.9.5-S11: Cổ phiếu — bảng giá portfolio + query CK theo mã

**Labels:** `story`, `phase-3.9.5`, `market`, `feature`
**Parent:** Epic 4
**Estimate:** 0.5 ngày

### Description
Bảng giá hiện show all stocks (overwhelming). Pattern mới: filtered theo portfolio user; thêm query "tìm CK theo mã" cho cases ngoài portfolio.

### Acceptance Criteria
- [ ] Default view "Bảng giá" filtered theo `user.portfolio.stocks`
- [ ] Empty portfolio → empty state với hint "Thêm CK vào portfolio để theo dõi"
- [ ] Button "🔍 Tìm CK theo mã" → user gõ mã (e.g. "VNM") → show quote
- [ ] Query path tận dụng SSI provider từ Phase 3.9
- [ ] Cache 5 phút (consistent với stock TTL)
- [ ] Invalid ticker → friendly error (không crash)

### Technical Notes
- Files: `backend/intent/handlers/query_portfolio.py`, `backend/intent/handlers/query_market.py`, `backend/services/portfolio_service.py`
- Query handler có thể là free-form text intent với extracted ticker

### Dependencies
None. Phase 3.9 SSI provider already in place.

---

## [Story] P3.9.5-S12: Perf Tiền số — target p95 < 2s

**Labels:** `story`, `phase-3.9.5`, `market`, `perf`, `bug`
**Parent:** Epic 4
**Estimate:** 0.75 ngày

### Description
Tab Tiền số chậm (anecdotal > 5s). Apply pattern Gold đã optimize trong Phase 3.9 (cache + last_known fallback).

### Acceptance Criteria
- [ ] Identify root cause (provider latency, missing cache, no batching, sync LLM call?)
- [ ] Apply fix theo pattern Gold:
  - Redis cache TTL 120s
  - last_known fallback nếu provider down
  - Batch fetch nếu portfolio > 1 coin
- [ ] Benchmark test: render Tiền số view với portfolio 3 coins
  - p95 < 2s (cached)
  - p95 < 4s (cold)
- [ ] Stale-data banner nếu fallback to last_known
- [ ] No new ruff warnings

### Technical Notes
- Files: `backend/services/market_service.py`, `backend/intent/handlers/query_market.py`, market data provider layer (CoinGecko)
- Reuse `app/market_data/cache/price_cache.py` từ Phase 3.9
- Reuse Dispatcher pattern với circuit breaker

### Dependencies
None. Phase 3.9 cache infrastructure available.

---

## [Story] P3.9.5-S13: BUG — "Portfolios của tôi" trong Tiền số nhảy sang Chứng khoán

**Labels:** `story`, `phase-3.9.5`, `market`, `bug`, `P1`
**Parent:** Epic 4
**Estimate:** 0.5 ngày

### Description
Action `("market", "crypto", "portfolio")` đang dispatch sai → mở stock portfolio thay vì crypto. Bug này blocking crypto Portfolios feature hoàn toàn.

### Acceptance Criteria
- [ ] Reproduce bug trong dev, log dispatch path
- [ ] Fix routing: crypto portfolio button → `QUERY_PORTFOLIO` với `asset_type: "crypto"` (không default "stock")
- [ ] Regression test: click crypto portfolio → response chứa coins, không phải stocks
- [ ] Audit Vàng portfolio cùng pattern (no same bug)
- [ ] Audit BĐS portfolio nếu có

### Technical Notes
- Files: `backend/bot/handlers/menu_handler.py` (action routing dict), `backend/intent/handlers/query_portfolio.py` (asset_type param handling)
- Suspected: missing `asset_type` param trong routing dict, default fall through to "stock"

### Dependencies
None. Should ship Day 1.

---

## [Story] P3.9.5-S14: Button "Sửa tài sản" filtered theo type đang xem

**Labels:** `story`, `phase-3.9.5`, `market`, `ux`
**Parent:** Epic 4
**Estimate:** 0.5 ngày

### Description
User đang xem Crypto Portfolios muốn edit 1 coin → hiện phải đi qua menu Tài sản. Add button "Sửa tài sản" ngay trong Portfolios view, filtered theo asset_type.

### Acceptance Criteria
- [ ] Mỗi Portfolios view (stocks / crypto / gold) có button "✏️ Sửa tài sản"
- [ ] Click → list filtered theo asset_type đang xem (reuse logic từ S3)
- [ ] Edit flow giữ context: sau khi edit xong → quay về Portfolios view, không phải về menu Tài sản
- [ ] Consistent label & placement cho 3 asset types
- [ ] Empty state: "Chưa có tài sản loại này"

### Technical Notes
- Files: `backend/intent/handlers/query_portfolio.py`, `backend/bot/handlers/asset_entry.py`
- Callback data: `portfolio:edit:<asset_type>` để giữ return context

### Dependencies
S3 (shared filter helper).

---

## [Story] P3.9.5-S15: Hint UX cho Vàng → Portfolios của tôi

**Labels:** `story`, `phase-3.9.5`, `market`, `copy`
**Parent:** Epic 4
**Estimate:** 0.25 ngày

### Description
Sub-menu Vàng → Portfolios không có hint giải thích. Add hint string + audit consistency với stocks/crypto.

### Acceptance Criteria
- [ ] Thêm hint string ở submenu Vàng → Portfolios trong `content/menu_copy.yaml`
- [ ] Hint giải thích: "Đây là toàn bộ vàng bạn đang nắm giữ, định giá theo SJC realtime"
- [ ] vi-localization-checker pass
- [ ] Apply consistent hint cho stocks/crypto Portfolios nếu thiếu
- [ ] Bé Tiền tone consistent

### Technical Notes
- Pure content YAML

### Dependencies
None.

---

## [Story] P3.9.5-S16: Rename "Vàng JSC" → "Vàng"

**Labels:** `story`, `phase-3.9.5`, `market`, `copy`
**Parent:** Epic 4
**Estimate:** 0.1 ngày

### Description
Button "Vàng JSC" có 2 vấn đề: (1) "JSC" không phải brand chuẩn (đúng là "SJC"), (2) label nên ngắn gọn vì context đã rõ.

### Acceptance Criteria
- [ ] Button "🥇 Vàng JSC" → "🥇 Vàng" trong `content/menu_copy.yaml` (`submenu_market.buttons`)
- [ ] Backend metadata vẫn giữ `category: "gold"`, primary provider SJC
- [ ] Inside view có thể clarify "Giá theo SJC" trong intro hoặc footer
- [ ] No test snapshot break

### Technical Notes
- Pure content YAML

### Dependencies
None.

---

# Epic 5: Telegram Animation Emojis

**Label:** `epic`, `phase-3.9.5`, `emoji`, `polish`
**Estimate:** 1 ngày (~Day 6)
**Goal:** Upgrade từ static Unicode emoji sang Telegram premium animation emoji ở high-frequency touchpoint.

**Stories:** S17, S18, S19

---

## [Story] P3.9.5-S17: Audit static emoji + lập mapping

**Labels:** `story`, `phase-3.9.5`, `emoji`, `audit`
**Parent:** Epic 5
**Estimate:** 0.4 ngày

### Description
Grep tất cả static emoji trong user-facing strings, tạo mapping → Telegram premium animation emoji ID.

### Acceptance Criteria
- [ ] Grep output list top 20-30 emoji theo frequency
- [ ] File mới `content/emoji_animation_map.yaml` với schema:
  ```yaml
  money_bag:
    static: 💰
    animation_id: "5368324170671202286"
    contexts: [briefing, milestones]
  ```
- [ ] Map cover ít nhất: 💰 💎 🎯 📊 📈 📉 💡 🔥 ✅ 🎉 ⚠️ 💸 🏆 📅 💼
- [ ] Document source của animation_id (Telegram official emoji pack hoặc custom pack)
- [ ] vi-localization-checker compatibility (animation emoji không break copy parsing)

### Technical Notes
- animation_id collected từ Telegram emoji search hoặc Bot API `getCustomEmojiStickers`
- Lưu trong content YAML để dễ maintain

### Dependencies
None.

---

## [Story] P3.9.5-S18: Helper utility render animation emoji

**Labels:** `story`, `phase-3.9.5`, `emoji`, `infra`
**Parent:** Epic 5
**Estimate:** 0.3 ngày

### Description
Helper utility convert string với emoji → tuple (text, MessageEntity[]) để Telegram render animation.

### Acceptance Criteria
- [ ] Function `render_with_animation(text: str, mapping: dict) → tuple[str, list[MessageEntity]]`
- [ ] Emoji có trong mapping → entity `type=custom_emoji, custom_emoji_id=...`
- [ ] Emoji không có mapping → giữ nguyên static (no entity)
- [ ] Telegram adapter accept entities param, pass qua `send_message`
- [ ] Unit test 3 cases: all mapped, partial, none
- [ ] Layer contract: utility lives in `backend/bot/utils/`, adapter handles transport

### Technical Notes
- Files: `backend/bot/utils/emoji_renderer.py` (new), `backend/adapters/telegram_adapter.py` (extend send_message signature)
- MessageEntity offset/length cần đúng UTF-16 code units (Telegram standard)

### Dependencies
S17 (mapping file).

---

## [Story] P3.9.5-S19: Integration ở touchpoint chính

**Labels:** `story`, `phase-3.9.5`, `emoji`, `integration`
**Parent:** Epic 5
**Estimate:** 0.3 ngày

### Description
Apply animation emoji helper ở high-frequency touchpoint user gặp thường xuyên nhất.

### Acceptance Criteria
- [ ] Morning briefing dùng animation cho 💰 (net worth), 📈/📉 (delta), 🌤️ (greeting)
- [ ] Milestone celebrations dùng animation 🎉 + 🏆
- [ ] Transaction success confirmations dùng animation ✅
- [ ] Submenu intros (Tài sản / Cashflow / Market / Goals) dùng animation cho header emoji
- [ ] Rest of bot giữ static (giảm scope, target high-impact only)
- [ ] Manual smoke test: gửi briefing tới Telegram premium account → emoji animate
- [ ] Manual smoke test: gửi tới non-premium → fallback static, no error

### Technical Notes
- Files: `backend/bot/handlers/briefing.py`, `backend/services/milestone_service.py`, `backend/bot/handlers/menu_handler.py`, `backend/bot/handlers/transaction.py`
- Telegram tự fallback to static emoji nếu user không premium — no extra logic needed

### Dependencies
S17, S18.

---

## 📊 Summary

| Epic | Stories | Estimate | Priority |
|------|---------|----------|----------|
| Epic 1: Wealth | S1, S2, S3 | 1.25 ngày | Medium |
| Epic 2: Dashboard | S4, S5 | 0.75 ngày | Medium |
| Epic 3: Cashflow | S6-S10 | 2 ngày | Medium |
| Epic 4: Market | S11-S16 | 2 ngày | **Highest (P1 bugs)** |
| Epic 5: Emoji | S17-S19 | 1 ngày | Low (polish) |
| **Total** | **19 stories** | **~7 ngày** | |

---

## 🏷️ GitHub Labels Setup

Create labels nếu chưa có:
- `phase-3.9.5` (color: same family as phase-3.9)
- `epic` (existing)
- `story` (existing)
- `ux-polish` (new)
- `emoji` (new)
- Sub-labels: `wealth`, `dashboard`, `cashflow`, `market` (existing or new)

---

*Document version: 1.0 — initial draft 2026-05-10*
