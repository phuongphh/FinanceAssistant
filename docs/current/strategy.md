# Personal CFO Assistant — Product Strategy V2

> **Đây là phiên bản thứ 2 của strategy, reflects quyết định lớn về positioning: chuyển từ "finance assistant" sang "Personal CFO cho người Việt".**

---

## 🎯 Vision Statement

**Xây dựng Personal CFO đầu tiên cho tầng lớp trung lưu Việt Nam** — một AI assistant không chỉ tracking chi tiêu, mà giúp user **xây dựng, quản lý và tối ưu hóa tài sản cá nhân** qua mọi giai đoạn cuộc đời.

Chúng ta không compete với Money Lover, MISA, Spendee. Chúng ta tạo ra một category mới ở VN: **Personal Wealth Management for Mass Affluent**.

---

## 🎨 Positioning Shift (Quan Trọng Nhất)

### Từ "Finance Assistant" → "Personal CFO"

| Finance Assistant (Old) | Personal CFO (New) |
|-------------------------|---------------------|
| Theo dõi chi tiêu | Quản lý **giá trị ròng (net worth)** |
| Giúp tiết kiệm | Giúp **xây dựng tài sản** |
| "Tháng này chi gì?" | "Tài sản mình tăng/giảm?" |
| Target: chưa có tài sản | Target: **đã hoặc đang xây tài sản** |
| Value: không vượt ngân sách | Value: **tăng net worth lâu dài** |
| Competitor: MISA, Money Lover | **Không có đối thủ trực tiếp ở VN** |
| Content focus: tiết kiệm | Content focus: **đầu tư + wealth** |

**Khoảng trống thị trường:** Tại VN hiện tại:
- **MISA/Money Lover:** Serve người chưa có tài sản
- **Finhay/Tikop:** Single-asset investment apps
- **Private banking:** Chỉ serve >10 tỷ VND
- **Gap rộng:** Người có 500tr-5 tỷ → **không ai serve**

Đây chính là segment bạn nhắm đến — **mass affluent gap**.

---

## 👥 Target User — "Ladder of Engagement"

Sản phẩm phải hấp dẫn cả 4 levels, user level up tự nhiên:

### Level 0: Starter (Tài sản 0-30tr)
**User điển hình:** 22-25 tuổi, mới đi làm, lương 10-20tr, chưa có đầu tư
- **Focus:** Xây thói quen tracking, hiểu net worth
- **Tính năng core:** Expense tracking đơn giản, cash balance, vision "đường đi"
- **Hook tâm lý:** *"Đây là con số tài sản của bạn hôm nay — xem nó tăng mỗi ngày"*
- **Educational:** Bot dạy basic về đầu tư, lãi kép, mục tiêu

### Level 1: Young Professional (30-200tr)
**User điển hình:** 26-32 tuổi, lương 20-40tr, có tiết kiệm, bắt đầu quan tâm đầu tư
- **Focus:** Mở đầu tư đầu tiên, xây danh mục
- **Tính năng:** + Stock tracking, + goal setting, + quỹ mở
- **Hook:** *"Bạn đủ điều kiện để bắt đầu đầu tư. Đây là các bước..."*

### Level 2: Mass Affluent (200tr-1 tỷ)
**User điển hình:** 30-45 tuổi, thu nhập 30-80tr, có 1 nhà, có chứng khoán
- **Focus:** Đa dạng hóa, rental income
- **Tính năng:** + Multiple assets, + rental tracking, + tax planning
- **Hook:** *"Tài sản bạn có thể tối ưu hơn. Dưới đây là đề xuất..."*

### Level 3: High Net Worth (1 tỷ+)
**User điển hình:** 40-55 tuổi, executive/entrepreneur, portfolio đa dạng
- **Focus:** Tối ưu, planning nghỉ hưu, estate
- **Tính năng:** Full CFO suite, inheritance planning, alternative investments

**Chiến lược "Ladder":** User không cần biết họ ở level nào. App **tự động adapt** UI và suggestions theo net worth hiện tại. Khi user "tốt nghiệp" level → bot congratulate và unlock features mới.

---

## 🏛️ 3 Trụ Cột Sản Phẩm

### Trụ Cột 1: Wealth Tracking & Management
**Theo dõi tổng tài sản qua mọi loại**
- Tiền mặt + tài khoản ngân hàng
- Chứng khoán + quỹ đầu tư
- Bất động sản (ở + cho thuê + đầu tư)
- Crypto
- Vàng (SJC, PNJ)
- Tài sản khác (xe, đồ sưu tầm...)

**Daily visualization:** Net worth hôm nay, so với tuần trước, tháng trước, năm trước.

### Trụ Cột 2: Cashflow Intelligence
**Hiểu dòng tiền thực sự**
- Thu: Lương + thụ động (thuê nhà, cổ tức, lãi)
- Chi: Cố định + Lifestyle + Đầu tư
- Tỷ lệ tiết kiệm
- Runway (nếu mất việc, sống được bao lâu?)

**Key insight:** Thay vì tracking từng giao dịch 50k cafe, focus vào **cashflow categories** ở mức cao hơn.

### Trụ Cột 3: Investment Intelligence
**AI-driven recommendations**
- Market updates mỗi sáng
- Rebalancing suggestions
- Opportunity alerts (lãi suất bank nào tốt, VN-Index điểm vào đẹp)
- Goal tracking (retire bao nhiêu, cần đầu tư gì)

---

## 🔄 3 Tier Expense Tracking

User không muốn ghi từng ly cafe, nhưng muốn biết chi tiêu lớn. Giải pháp:

### Tier 1 — Micro (<200k): Không track chi tiết
Gộp vào "Lifestyle spending" aggregate. User chỉ cần biết "tháng này lifestyle 15tr".

### Tier 2 — Medium (200k - 2tr): Storytelling
Bot hỏi mỗi sáng *"Hôm qua anh có chi gì đáng kể không?"* — user kể bằng voice hoặc text.

### Tier 3 — Major (>2tr): Active capture
Bot **proactive** detect qua SMS, OCR, hoặc hỏi trực tiếp. Track chi tiết với category riêng (electronics, healthcare, travel, luxury...).

**Thresholds cá nhân hóa theo thu nhập:**
- Lương 15tr: Medium = 100k-500k
- Lương 40tr: Medium = 200k-2tr
- Lương 80tr: Medium = 500k-3tr

Bot tự tính và adjust.

---

## 📋 Roadmap Mới (V2)

> **Auto-synced** từ
> [`phase-status.yaml`](phase-status.yaml). Phần phía dưới giữa các
> marker được regenerate bởi `scripts/sync_phase_status.py` — đừng
> sửa tay. Bốn dòng mô tả chi tiết cho mỗi phase nằm bên DƯỚI bảng
> (auto-table chỉ cho overview).

<!-- BEGIN: phase-status:current-line -->
🚀 **Phase 3.7: Agent Architecture** (current) — [detail](docs/current/phase-3.7-detailed.md)
<!-- END: phase-status:current-line -->

<!-- BEGIN: phase-status:roadmap-table -->
| Phase | Status | Duration | Detailed Doc | Description |
|---|---|---|---|---|
| Phase 1: UX Foundation | ✅ done | 3 tuần | [phase-1-detailed.md](docs/current/phase-1-detailed.md) | Telegram bot + manual entry + monthly report + Notion dashboard |
| Phase 2: Personality & Care | ✅ done | 3 tuần | [phase-2-detailed.md](docs/current/phase-2-detailed.md) | Onboarding, Bé Tiền tone, milestone celebration, empathy engine |
| Phase 3A: Wealth Foundation | ✅ done | 4 tuần | [phase-3a-detailed.md](docs/current/phase-3a-detailed.md) | Asset model, net worth, morning briefing, Mini App dashboard |
| Phase 3.5: Intent Understanding Layer | ✅ done | 3 tuần | [phase-3.5-detailed.md](docs/current/phase-3.5-detailed.md) | Rule + LLM intent classifier, confirm/clarify, advisory, voice queries |
| Phase 3.6: Menu UX Revamp | ✅ done | 1.5 tuần | [phase-3.6-detailed.md](docs/current/phase-3.6-detailed.md) | Wealth-first 3-level menu, adaptive intros, hard cutover from V1 flat menu |
| **Phase 3.7: Agent Architecture** | 🔨 current | 3 tuần | [phase-3.7-detailed.md](docs/current/phase-3.7-detailed.md) | Two-tier agent (DB-Agent + Premium Reasoning), tool-use, orchestrator routing |
| Phase 3B: Market Intelligence | 📋 next | TBD | [phase-3b-outline.md](docs/current/phase-3b-outline.md) | Real market data, advisory deepening, portfolio analytics |
| Phase 4: Investment Intelligence | 🔮 planned | TBD | — | Investment Twin, scenario modeling, rental property tracking |
| Phase 5: Behavioral Engine | 🔮 planned | TBD | — | Wealth-aware nudges, Financial DNA, anomaly detection |
| Phase 6: Scale & Commercialize | 🔮 planned | TBD | — | Public beta, subscriptions, multi-region, household mode |
<!-- END: phase-status:roadmap-table -->


### Phase 1: UX Foundation
**Thời gian:** 3-4 tuần
- Rich messages, inline buttons, Mini App, visual identity

### Phase 2: Personality & Care
**Thời gian:** 2-3 tuần
- Onboarding, memory moments, empathy, surprise & delight

### Phase 3A: Wealth Foundation ⭐
**Thời gian:** 4 tuần
- Net worth calculator + data model
- Manual asset entry (BĐS, stocks, crypto, cash, vàng)
- Morning briefing (basic, chưa market data)
- Simple storytelling expense (threshold-based)

### Phase 3.5: Intent Understanding Layer ⭐ NEW
**Thời gian:** 3 tuần (added giữa 3A và 3B sau khi phát hiện gap về free-form text)
- Rule-based intent classifier (75% queries, zero LLM cost)
- LLM fallback (DeepSeek, ~$0.0001/call) cho queries lạ
- Confidence-based dispatcher: execute / confirm / clarify
- Personality wrapper + wealth-level adaptive responses
- Advisory handler với rich context + legal disclaimer
- Voice queries → intent pipeline (storytelling fallback)
- Admin metrics endpoint + pattern improvement loop

### Phase 3B: Market Intelligence
**Thời gian:** 3 tuần
- Stock price integration (SSI/VNDIRECT)
- Crypto price (CoinGecko)
- Gold price (SJC/PNJ)
- Bank rate comparisons
- Enhanced morning briefing với real-time data

### Phase 4: Investment Intelligence
**Thời gian:** 4-5 tuần
- Portfolio analytics (sharpe, volatility, diversification)
- Rental income tracking (Case B properties)
- Goal setting & projection
- Rebalancing suggestions

### Phase 5: Behavioral Engine (Wealth-Aware)
**Thời gian:** 4-5 tuần
- Financial DNA (behaviors)
- Wealth growth patterns
- Optimal Twin (so với user có income tương tự)
- Micro-interventions for wealth building

### Phase 6: Scale & Commercialize
**Thời gian:** Ongoing
- Web PWA dashboard
- Zalo Mini App
- Household mode (vợ chồng cùng quản lý)
- Pricing tiers

**Tổng thời gian MVP commercializable: ~5-6 tháng**

---

## 💰 Pricing Strategy (Mới)

Positioning Personal CFO cho phép pricing cao hơn nhiều:

### Free Tier
- Expense tracking basic
- Net worth tính thủ công
- 1 loại asset

### Pro (149k/tháng hoặc 1.49tr/năm)
- Tất cả loại assets
- Morning briefing đầy đủ
- Market intelligence
- Financial DNA
- Target: Level 0-1 users

### CFO (399k/tháng hoặc 3.99tr/năm)
- Tất cả Pro features
- Rental income tracking
- Portfolio analytics advanced
- Investment Twin
- Monthly 1-1 call với financial advisor (partnership)
- Target: Level 2-3 users

**Benchmark:** So với advisor truyền thống (10-20tr/tháng), CFO tier là 1/25 giá — vẫn premium so với Money Lover (49k) nhưng justified bởi value.

---

## 🔑 Competitive Moats

### 1. AI-Native từ core
Không thể bắt chước bằng việc thêm AI vào app expense tracker. Kiến trúc từ đầu xây quanh LLM conversation.

### 2. Storytelling data
Data thu được từ storytelling **giàu hơn nhiều** so với SMS parsing. Có emotion, context, social signals → Phase 5 (Behavioral) có input quality cao.

### 3. Vietnam-specific intelligence
- Hiểu market VN (VN-Index, BĐS VN, bank rates VN)
- Content tiếng Việt có hồn
- Seasonal events VN (Tết, Trung thu, etc.)
- Bank format parsing cho bank VN

### 4. Ladder of Engagement
User grow với app. Người ở Level 0 hôm nay là Level 2 customer 3 năm sau. Đây là **LTV moat** — đối thủ chỉ serve 1 segment, chúng ta serve cả ladder.

---

## 📊 Key Metrics (Đã Điều Chỉnh)

### Activation (Phase 1-2)
- % user hoàn thành onboarding (target: >70%)
- Time to first asset entry (target: <10 phút)

### Engagement (Phase 3+)
- **Daily Morning Briefing open rate** (key metric mới — target: >60%)
- Avg assets tracked per user (target: >3 loại)
- Storytelling participation (target: >50% days)

### Retention
- D7 / D30 retention (target: 70% / 50%)
- Monthly active net worth viewers (target: >80% of registered)

### Wealth-specific
- **Average net worth tracked per user** (tăng theo thời gian → signal trust)
- **Asset diversity score** (bao nhiêu loại asset/user)
- % users có asset ngoài cash (target: >40% sau 3 tháng)

### Satisfaction
- NPS (target: >50)
- % users refer to friends (target: >20%)

---

## ⚠️ Risks & Mitigation

| Risk | Mitigation |
|------|-----------|
| User không trust app với financial data | Start với non-sensitive (mostly read-only), earn trust, add sensitive later |
| Market data APIs unreliable | Multiple sources redundancy (SSI + VNDIRECT, CoinGecko + Binance) |
| Người trẻ cảm thấy "không đủ tài sản" để dùng | "Net worth từ ngày đầu" messaging + educational content |
| Compete với Finhay/Tikop khi họ add tracking | Moat là **tổng hợp đa asset** (họ chỉ làm 1 loại) |
| Bất động sản data khó có chính xác | User-input model, bot chỉ suggest từ batdongsan.com |
| Regulatory (VN về finance advice) | Disclaimer rõ: "thông tin tham khảo, không phải tư vấn đầu tư" |

---

## 🎯 Guiding Principles (Cập nhật V2)

1. **Wealth-first, expense-second** — Net worth là North Star, expense là supporting
2. **Ladder design** — App adapt theo user level, không one-size-fits-all
3. **Empowerment, not shame** — Framing positive (tăng tài sản), không negative (hạn chế chi tiêu)
4. **AI-native, không AI-added** — Mọi feature design với LLM ở core
5. **VN-specific** — Hiểu thị trường, văn hóa, ngôn ngữ Việt
6. **Ship sớm, validate, iterate** — Phase độc lập có giá trị, không làm hết mới release

---

## 📝 Changelog

**V2 (current):** Pivot to Personal CFO positioning
- Phase 3 rewritten from "Zero-Input Capture" to "Wealth Foundation"
- Added Ladder of Engagement user model
- Introduced 3-tier expense tracking
- Added market intelligence as core
- Pricing moved upmarket

**V1 (archived as strategy.md):** Original "finance assistant" strategy

---

**Good luck với vision lớn! 🚀**
