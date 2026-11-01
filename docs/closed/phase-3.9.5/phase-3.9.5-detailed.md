# Phase 3.9.5 — Pre-Launch UX Polish (Chi Tiết Triển Khai)

> **Đây là phase nhỏ, inserted giữa Phase 3.9 và Phase 4A, để chuẩn bị cho soft launch tháng 6/2026 với foundation sạch.**
>
> **Thời gian ước tính:** 5-7 ngày (với Claude Code velocity)
> **Mục tiêu cuối Phase:** 11 dogfooding findings được khắc phục, 2 menu rename, plus full upgrade từ static emoji sang Telegram premium animation emoji ở các touchpoint chính.
> **Điều kiện "Done":** Tất cả 5 Epic ship, regression test pass, vi-localization-checker + layer-contract-checker clean, soft launch playbook ready.
>
> **Prerequisites:** Phase 3.9 (market data real) đã ship. Polish này build trên menu hiện hữu (Tài sản / Dashboard / Dòng tiền / Thị trường) — không thêm new domain logic.

---

## 🎯 Triết Lý Thiết Kế Phase 3.9.5

5 nguyên lý quan trọng:

### 1. "Foundation Before Flash"
Theo strategy V3 (Guiding Principle #4): polish foundation TRƯỚC khi build Twin (Phase 4A). Twin sẽ reuse menu Tài sản / Dòng tiền / Thị trường làm entry point và data source — bug ở foundation sẽ được Twin kế thừa và khuếch đại.

### 2. "Functional Bugs Are Not Polish"
Ít nhất 3/19 Stories là defect thật (không phải cosmetic):
- S2: Logic YTD return sai
- S12: Perf Tiền số chậm > 2s
- S13: Routing bug "Portfolios của tôi" trong Tiền số nhảy sang Chứng khoán

→ Treat như P1 bugs, không phải tech debt nice-to-have.

### 3. "Anti-Form, Click-to-Edit"
Dashboard hiện tại là static report. Phase này thêm khả năng click vào dòng tài sản → mở edit flow của tài sản đó (S4). Match tinh thần "anti-form" của Phase 3.8.5 — surface action ở chính nơi user đang nhìn data.

### 4. "Consistent Patterns Across Asset Types"
Stocks / Crypto / Gold hiện nay xử lý không đồng nhất (Gold đã được optimize Phase 3.9, Crypto chưa; Stocks có "Sửa tài sản" gián tiếp, Crypto/Gold không có). Phase này chuẩn hoá pattern "Portfolios của tôi" + "Sửa tài sản (filtered theo type)" cho cả 3 loại.

### 5. "Premium Feel Through Animation Emojis"
Telegram premium animation emojis tăng cảm giác "alive" của bot mà không tốn dev effort lớn. Apply ở high-frequency touchpoint: morning briefing, milestone celebrations, success confirmations, menu intros.

---

## 📅 Phân Bổ Thời Gian (5-7 ngày)

| Ngày | Epic | Deliverable |
|------|------|-------------|
| **Ngày 1** | Epic 4 (S12, S13) — Market bugs | Crypto routing fix + perf < 2s |
| **Ngày 2** | Epic 4 (S11, S14, S15, S16) — Market polish | Bảng giá portfolio, button "Sửa tài sản", hint Vàng, rename "Vàng JSC" → "Vàng" |
| **Ngày 3** | Epic 1 (S1, S2, S3) — Wealth menu | Xoá copy thừa, fix YTD button, gating xoá tài sản |
| **Ngày 4** | Epic 2 (S4, S5) + Epic 3 (S6, S7) — Dashboard + Cashflow part 1 | Click-to-edit dashboard, rename "Báo cáo", label fixes, dedupe |
| **Ngày 5** | Epic 3 (S8, S9, S10) — Cashflow part 2 | Tách card Thu/Chi, báo cáo "Dòng tiền tháng này", link Goals |
| **Ngày 6** | Epic 5 (S17, S18, S19) — Telegram animation emojis | Audit, mapping, integration ở touchpoint chính |
| **Ngày 7** | Regression + polish | Manual TC pass, vi-localization-checker, layer-contract-checker, prep release notes |

**Critical path:** Epic 4 (highest priority — bugs + perf) → Epic 1+2 (independent, low risk) → Epic 3 (largest scope) → Epic 5 (touch nhiều file YAML, làm cuối cùng).

---

## 🗂️ Cấu Trúc Thay Đổi (Files Touched)

```
finance_assistant/
├── content/
│   ├── menu_copy.yaml                   # ⭐ HEAVY — rename, dedupe, new buttons, hints
│   ├── briefing.yaml                    # 🎨 emoji upgrade
│   ├── briefing_templates.yaml          # 🎨 emoji upgrade
│   └── empathy_messages.yaml            # 🎨 emoji upgrade
│
├── backend/
│   ├── bot/handlers/
│   │   ├── menu_handler.py              # ⭐ HEAVY — Cashflow new actions, Market routing
│   │   ├── asset_entry.py               # ⭐ — Type-first delete flow (S3), edit-from-dashboard (S4), button "Sửa tài sản" filtered (S14)
│   │   ├── briefing.py                  # 🎨 emoji upgrade
│   │   └── transaction.py               # 🎨 emoji upgrade
│   │
│   ├── intent/handlers/
│   │   ├── query_market.py              # ⭐ — Crypto perf (S12), routing fix (S13)
│   │   ├── query_portfolio.py           # ⭐ — Bảng giá filter (S11), button "Sửa tài sản" (S14)
│   │   └── query_cashflow.py            # ⭐ — Tách card Thu/Chi (S8), monthly report (S9)
│   │
│   ├── services/
│   │   ├── wealth_dashboard_service.py  # ⭐ — Click-to-edit metadata (S4)
│   │   ├── portfolio_service.py         # ⭐ — Crypto query optimization (S12)
│   │   └── market_service.py            # ⭐ — Apply Gold cache pattern to Crypto (S12)
│   │
│   └── bot/formatters/
│       ├── menu_formatter.py            # 🎨 emoji upgrade
│       └── dashboard_formatter.py       # ⭐ — Click-to-edit serialization (S4)
│
└── tests/
    └── test_phase_3_9_5/
        ├── test_market_routing.py       # S13 regression test
        ├── test_market_perf.py          # S12 perf benchmark
        ├── test_cashflow_cards.py       # S6-S10
        └── test_emoji_render.py         # S17-S19 smoke
```

**Note:** Phase 3.9.5 KHÔNG thêm migration mới, KHÔNG thêm agent tools. Pure UX layer + perf + bug fix.

---

## 🔧 Epic 1 — Tài sản (Wealth Menu Polish)

**Goal:** Loại bỏ UX debt trong submenu Tài sản — xoá câu copy thừa, fix logic button, gating cho destructive action.

### S1 — Xoá câu "Đây là hình ảnh..." trong Tổng tài sản

**Layer:** content YAML
**File:** `content/menu_copy.yaml` → `action_assets_net_worth.market_value_note` hoặc tương đương
**Issue gốc:** Câu này dài, redundant với context, làm rối view.

**Acceptance:**
- [ ] Identify exact YAML key chứa câu "Đây là hình ảnh..."
- [ ] Xoá câu (hoặc thay bằng empty string nếu key vẫn được referenced)
- [ ] Render view "Tổng tài sản" không còn câu này
- [ ] vi-localization-checker pass

### S2 — Bỏ button "Phân bổ chi tiết" + sửa logic button YTD return

**Layer:** content YAML + handler
**Files:** `content/menu_copy.yaml` (button labels), `backend/bot/handlers/menu_handler.py` (`_action_assets_*`), `backend/intent/handlers/query_assets.py`
**Issue gốc:**
1. Button "Phân bổ chi tiết" trùng chức năng với view khác → bỏ
2. Button "YTD return" hiện tại logic sai (cần verify: tính sai range, tính sai base, hay return wrong field?)

**Acceptance:**
- [ ] Button "Phân bổ chi tiết" bị xoá khỏi menu báo cáo chi tiết tài sản
- [ ] YTD return computed đúng: từ 1/1/current_year → today, base = net worth tại 1/1, return = (current - base) / base
- [ ] Edge case: account < 1 năm → fallback "Từ ngày tham gia"
- [ ] Unit test cho YTD calc với 3 cases: full year, partial year (< 12 months), zero base

### S3 — Flow xoá tài sản: chọn type trước

**Layer:** handler
**File:** `backend/bot/handlers/asset_entry.py`
**Issue gốc:** Hiện tại "Xoá tài sản" liệt kê hết tất cả → quá dài, dễ chọn nhầm. Pattern mới: chọn type trước (cổ phiếu / crypto / vàng / BĐS / cash) → list filtered.

**Acceptance:**
- [ ] User click "Xoá tài sản" → menu chọn asset type (5-6 buttons)
- [ ] Sau khi chọn type → list filtered chỉ assets của type đó
- [ ] Mỗi row vẫn có button "Xoá" với confirmation step
- [ ] Empty type → message "Không có tài sản loại này"
- [ ] Reuse type filter logic với S14 (DRY)

---

## 🔧 Epic 2 — Dashboard

**Goal:** Dashboard từ static report → interactive (click-to-edit), rename ngắn gọn.

### S4 — Click vào dòng tài sản → mở edit flow

**Layer:** formatter + handler
**Files:** `backend/bot/formatters/dashboard_formatter.py`, `backend/services/wealth_dashboard_service.py`, `backend/bot/handlers/asset_entry.py`
**Issue gốc:** Dashboard "Báo cáo tài sản" liệt kê assets theo group nhưng không actionable. User muốn click vào row → edit asset đó.

**Acceptance:**
- [ ] Mỗi row asset trong dashboard có inline button hoặc callback `dashboard:edit:<asset_id>`
- [ ] Click → mở edit wizard của `asset_entry.py` cho asset đó (reuse existing edit flow)
- [ ] Nếu asset thuộc category với multiple instances (e.g. nhiều mã cổ phiếu) → show list chọn 1
- [ ] Edit thành công → quay về dashboard với data refreshed
- [ ] Layer contract: handler call service, không direct DB write

### S5 — Rename "Báo cáo tài sản" → "Báo cáo"

**Layer:** content YAML
**File:** `content/menu_copy.yaml` (dashboard title, menu button label)
**Issue gốc:** Title quá dài, "tài sản" đã rõ qua context.

**Acceptance:**
- [ ] Tất cả instance "Báo cáo tài sản" trong menu_copy.yaml → "Báo cáo"
- [ ] Header dashboard view hiển thị "📊 Báo cáo"
- [ ] Không break existing tests (search test snapshots cho "Báo cáo tài sản")

---

## 🔧 Epic 3 — Dòng tiền (Cashflow Menu)

**Goal:** Restructure Tổng quan để rõ ràng hơn, dedupe cards trùng, add Goals link, add monthly report.

### S6 — Sửa label "Dòng tiền hiện tại của từng tháng"

**Layer:** content YAML
**File:** `content/menu_copy.yaml` (`submenu_cashflow.intro` hoặc card titles)
**Issue gốc:** Label hiện tại không rõ user đang xem gì.

**Acceptance:**
- [ ] Label rõ: ví dụ "Dòng tiền tháng này" hoặc "Tình hình dòng tiền 30 ngày qua"
- [ ] Câu intro của Tổng quan submenu reflect đúng scope (current month + so sánh)
- [ ] vi-localization-checker pass

### S7 — Dedupe: bỏ "So sánh tháng trước" trùng Thu vs Chi + tỷ lệ tiết kiệm

**Layer:** content YAML + handler
**Files:** `content/menu_copy.yaml`, `backend/intent/handlers/query_cashflow.py`
**Issue gốc:** Card "So sánh với tháng trước" hiện tại overlap với "Thu vs Chi" và "Tỷ lệ tiết kiệm" → cùng số liệu, redundant.

**Acceptance:**
- [ ] Identify exact card đang hiển thị duplicate → ghi nhận trong PR description
- [ ] Bỏ phần trùng lặp (giữ "Thu vs Chi" + "Tỷ lệ tiết kiệm" làm canonical, bỏ comparison khỏi Tổng quan)
- [ ] Hoặc consolidate thành 1 card duy nhất với delta inline
- [ ] User test xem report Tổng quan thấy mỗi metric chỉ xuất hiện 1 lần

### S8 — Tách riêng card Thu nhập / Chi tiêu

**Layer:** handler + formatter
**Files:** `backend/intent/handlers/query_cashflow.py`, `backend/bot/formatters/`
**Issue gốc:** Hiện tại Thu nhập và Chi tiêu hiển thị chung 1 block → khó scan.

**Acceptance:**
- [ ] Tổng quan view có 2 cards độc lập: "💼 Thu nhập tháng" + "💸 Chi tiêu tháng"
- [ ] Mỗi card show: total + top 2-3 sources/categories + delta vs tháng trước
- [ ] Layout consistent với cards khác (header + total + breakdown)

### S9 — Thêm báo cáo "Dòng tiền tháng này"

**Layer:** content YAML + handler
**Files:** `content/menu_copy.yaml` (new button), `backend/bot/handlers/menu_handler.py` (new action), `backend/intent/handlers/query_cashflow.py` (new sub-handler)
**Issue gốc:** User muốn 1 báo cáo deep-dive cho tháng hiện tại (không phải Tổng quan compare 6 tháng).

**Acceptance:**
- [ ] Button mới "📅 Dòng tiền tháng này" trong submenu Cashflow
- [ ] Action key `("cashflow", "monthly_report")` → call `QUERY_CASHFLOW` với `focus: "current_month_detail"`
- [ ] Report content: thu nhập theo source, chi tiêu theo category, daily flow chart text, biggest transactions
- [ ] Vietnamese copy through `content/menu_copy.yaml`

### S10 — Thêm "Mục tiêu" link tới existing Goals

**Layer:** content YAML + handler routing
**Files:** `content/menu_copy.yaml` (new button), `backend/bot/handlers/menu_handler.py`
**Issue gốc:** User muốn truy cập Goals từ Cashflow context vì tiết kiệm và goals liên quan trực tiếp.

**Acceptance:**
- [ ] Button mới "🎯 Mục tiêu" trong submenu Cashflow
- [ ] Click → redirect sang submenu Goals existing (không tạo Goals layer mới)
- [ ] Implementation: action `("cashflow", "goals")` → dispatch tới `("goals", "list")` handler
- [ ] Test: từ Cashflow click Mục tiêu → goals list render đúng

---

## 🔧 Epic 4 — Thị trường (Market Menu)

**Goal:** Fix bug routing Crypto, perf < 2s, chuẩn hoá Portfolios pattern, rename, hint UX.

### S11 — Cổ phiếu: bảng giá portfolio + query CK theo mã

**Layer:** handler + service
**Files:** `backend/intent/handlers/query_portfolio.py`, `backend/intent/handlers/query_market.py`, `backend/services/portfolio_service.py`
**Issue gốc:** Bảng giá hiện tại show all stocks (overwhelm). Pattern mới: bảng giá chỉ show mã thuộc portfolio user; thêm query "tìm CK theo mã" cho cases ngoài portfolio.

**Acceptance:**
- [ ] Default view "Bảng giá" filtered theo `user.portfolio.stocks`
- [ ] Empty portfolio → empty state với hint "Thêm CK vào portfolio để theo dõi"
- [ ] Thêm command/button "🔍 Tìm CK theo mã" → user gõ mã (e.g. "VNM") → show quote
- [ ] Query path tận dụng SSI provider từ Phase 3.9
- [ ] Cache 5 phút (consistent với stock TTL)

### S12 — Perf Tiền số: target p95 < 2s

**Layer:** service + provider
**Files:** `backend/services/market_service.py`, `backend/intent/handlers/query_market.py`, market data provider layer
**Issue gốc:** Tab Tiền số hiện chậm (anecdotal > 5s). Gold đã được optimize trong Phase 3.9 (cache + last_known fallback). Apply same pattern.

**Acceptance:**
- [ ] Identify root cause: provider latency, missing cache, no batching, hay LLM call?
- [ ] Apply fix theo pattern Gold: Redis cache TTL 120s, last_known fallback, batch fetch nếu portfolio > 1 coin
- [ ] Add benchmark test: render Tiền số view với portfolio 3 coins → p95 < 2s (cached) / < 4s (cold)
- [ ] Stale-data banner nếu fallback to last_known

### S13 — BUG: "Portfolios của tôi" trong Tiền số nhảy sang Chứng khoán

**Layer:** handler routing
**Files:** `backend/bot/handlers/menu_handler.py`, `backend/intent/handlers/query_portfolio.py`
**Issue gốc:** Action `("market", "crypto")` → `("market", "crypto", "portfolio")` đang dispatch sai → mở stock portfolio.

**Acceptance:**
- [ ] Reproduce bug trong dev environment, log dispatch path
- [ ] Fix routing: crypto portfolio button → `QUERY_PORTFOLIO` với `asset_type: "crypto"` (không phải default "stock")
- [ ] Regression test: click crypto portfolio → response chứa coins, không phải stocks
- [ ] Apply same audit cho Vàng portfolio (đảm bảo không cùng bug)

### S14 — Button "Sửa tài sản" filtered theo type đang xem

**Layer:** handler
**Files:** `backend/intent/handlers/query_portfolio.py`, `backend/bot/handlers/asset_entry.py`
**Issue gốc:** User đang xem Crypto Portfolios muốn edit 1 coin → hiện phải đi qua menu Tài sản → chọn type → tìm. Better: button ngay trong Portfolios view.

**Acceptance:**
- [ ] Mỗi Portfolios view (stocks/crypto/gold) có button "✏️ Sửa tài sản"
- [ ] Click → list filtered theo asset_type đang xem (reuse logic từ S3)
- [ ] Edit flow giữ context: sau khi edit xong quay về Portfolios view
- [ ] Apply nhất quán cho 3 asset types

### S15 — Hint UX cho Vàng → Portfolios của tôi

**Layer:** content YAML
**File:** `content/menu_copy.yaml` (`submenu_market.gold.portfolio.hint` hoặc tương đương)
**Issue gốc:** Sub-menu Vàng → Portfolios không có hint giải thích user thấy gì.

**Acceptance:**
- [ ] Thêm hint string ở submenu Vàng → Portfolios
- [ ] Hint giải thích: "Đây là toàn bộ vàng bạn đang nắm giữ, định giá theo SJC realtime"
- [ ] vi-localization-checker pass
- [ ] Apply consistent hint cho stocks/crypto Portfolios nếu thiếu

### S16 — Rename "Vàng JSC" → "Vàng"

**Layer:** content YAML
**File:** `content/menu_copy.yaml` (`submenu_market.buttons`)
**Issue gốc:** "JSC" không phải brand chuẩn (đúng là SJC), và label nên ngắn gọn vì context đã rõ.

**Acceptance:**
- [ ] Button label "🥇 Vàng JSC" → "🥇 Vàng"
- [ ] Backend metadata vẫn giữ `category: "gold"` với primary provider SJC
- [ ] Inside view có thể clarify "Giá theo SJC" trong intro

---

## 🔧 Epic 5 — Telegram Animation Emojis

**Goal:** Upgrade từ static Unicode emoji sang Telegram premium animation emojis ở high-frequency touchpoint, nâng cảm giác "alive" của bot.

**Background:** Telegram Premium animation emojis được embed qua custom_emoji_id trong MessageEntity với type `custom_emoji`. Cần Telegram premium account để render — fallback về static emoji nếu user không có premium (Telegram tự handle).

### S17 — Audit static emoji + lập mapping

**Layer:** content YAML + code grep
**Files:** all `content/*.yaml`, `backend/bot/handlers/*.py`, `backend/bot/formatters/*.py`
**Output:** `content/emoji_animation_map.yaml`

**Acceptance:**
- [ ] Grep tất cả static emoji được dùng trong user-facing strings
- [ ] List top 20-30 emoji theo frequency (💰 💎 🎯 📊 📈 📉 💡 🔥 ✅ 🎉 ⚠️ 💸 ...)
- [ ] Map mỗi static emoji → 1 Telegram premium animation emoji ID (collect từ official Telegram emoji packs)
- [ ] YAML structure:
  ```yaml
  money_bag:
    static: 💰
    animation_id: "5368324170671202286"
    contexts: [briefing, milestones]
  ```
- [ ] vi-localization-checker compatibility (animation emoji không break copy parsing)

### S18 — Helper utility render animation emoji

**Layer:** util + adapter
**Files:** `backend/bot/utils/emoji_renderer.py` (new), `backend/adapters/telegram_adapter.py`
**Issue gốc:** Cần helper để chuyển static emoji string → MessageEntity với custom_emoji.

**Acceptance:**
- [ ] Function `render_with_animation(text: str, mapping: dict) → tuple[str, list[MessageEntity]]`
- [ ] Nếu emoji có trong mapping → tạo entity `type=custom_emoji, custom_emoji_id=...`
- [ ] Nếu không → giữ nguyên static
- [ ] Telegram adapter accept entities param, pass qua `send_message`
- [ ] Unit test với 3 cases: all mapped, partial, none

### S19 — Integration ở touchpoint chính

**Layer:** handlers + formatters
**Files:** `backend/bot/handlers/briefing.py`, `backend/services/milestone_service.py`, `backend/bot/handlers/menu_handler.py` (intros), `backend/bot/handlers/transaction.py` (success confirmations)
**Issue gốc:** Apply mapping ở các message user gặp thường xuyên nhất.

**Acceptance:**
- [ ] Morning briefing dùng animation emoji cho 💰 (net worth), 📈/📉 (delta), 🌤️ (greeting)
- [ ] Milestone celebration dùng animation 🎉 + 🏆
- [ ] Transaction success dùng animation ✅
- [ ] Submenu intros (Tài sản / Cashflow / Market / Goals) dùng animation cho header emoji
- [ ] Rest of bot giữ static (giảm scope, target high-impact only)
- [ ] Manual smoke test: gửi briefing tới Telegram premium account → emoji animate

---

## 📐 Layer Mapping & Contract Compliance

Theo CLAUDE.md layer contract, mọi changes phải tuân thủ:

| Story | Layer touched | Contract concern |
|-------|--------------|------------------|
| S1, S5, S6, S15, S16 | content YAML only | None — pure copy change |
| S2 | content + handler + service | Service tính YTD return, NO db.commit |
| S3 | handler | List filtered, không bypass service layer |
| S4 | formatter + handler + service | Edit flow reuse asset_entry, no direct DB |
| S7-S10 | content + handler | New action key registration in menu_handler routing dict |
| S11-S14 | handler + service | Service layer cache, NO db.commit, dispatcher pattern |
| S12 | service + provider | Reuse Phase 3.9 cache abstractions, no new commit pattern |
| S17-S19 | content + util + adapter | Adapter is the ONLY layer touching Telegram MessageEntity |

**Quality gates** (run before merge):
- `uv run ruff check .` — clean
- `uv run pytest tests/test_phase_3_9_5/` — all pass
- `code-explorer` agent verify no hardcoded Vietnamese strings introduced
- `layer-contract-checker` agent verify no boundary violations
- `vi-localization-checker` agent verify content YAML completeness

---

## ⚠️ Risk & Rollback

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| S13 routing bug có root cause sâu hơn dự kiến | Medium | Day 1 reproduce + log dispatch path, escalate nếu > 4h |
| S12 perf không đạt < 2s do upstream provider | Medium | Apply Gold cache pattern, accept p95 < 3s nếu provider hard limit |
| Animation emoji không render trên non-premium accounts | Low | Telegram tự fallback to static — verified behavior |
| Cashflow restructure break existing tests | Medium | Run pytest sau mỗi sub-task, không batch |
| Content YAML conflicts với i18n future plans | Low | Keys giữ Vietnamese-first naming consistent |

**Rollback strategy:**
- Per-Story commits → revert individual Story nếu regression
- Content YAML changes reversible via git
- S13 routing fix có feature flag environment var `MARKET_ROUTING_V2=true` để toggle nếu cần

---

## ✅ Definition of Done

Phase 3.9.5 considered DONE khi:

- [ ] Tất cả 19 Stories shipped với AC checked
- [ ] 5 Epic Issues closed trên GitHub
- [ ] Manual TC suite (60+ TC) signed off
- [ ] `phase-status.yaml` updated: 3.9.5 → done, 4A → current
- [ ] vi-localization-checker pass
- [ ] layer-contract-checker pass
- [ ] No new ruff warnings
- [ ] Pytest pass full suite
- [ ] Release notes (`phase-3.9.5-deploy-announcements.md`) written
- [ ] Soft launch checklist updated
- [ ] Branch `claude/enhance-ui-ux-phase-dkhqi` merged tới main

---

## 🚧 Out of Scope (Defer to Phase 4A)

- Twin entry points trong Dashboard (separate phase)
- Projection cards trong Cashflow (Twin job)
- Real-time price websocket (current pull-based đủ)
- Multi-currency display (single VND focus)
- Achievement badges trong dashboard (Phase 4.5)
- Web/Mini App parity của các fixes này (Phase 4A+ Mini App work)

---

*Document version: 1.0 — initial draft 2026-05-10*
*Update khi scope thay đổi hoặc discoveries trong implementation.*
