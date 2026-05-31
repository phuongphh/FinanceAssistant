# Personal CFO Assistant — Product Strategy V3

> **Phiên bản thứ 3 của strategy, sau khi Phase 3.7 (Agent Architecture) ship.**
> Đây là document consolidates strategic decisions sau strategic review session, định hình roadmap 10 tháng với target Tết 2027 launch.

---

> ⚠️ **Customer-facing language rule (NON-NEGOTIABLE).**
> "Personal CFO" is the **internal product positioning** used in strategy/architecture docs only. It MUST NEVER appear in user-facing text — welcome bubbles, briefings, chart watermarks, share images, soft-launch announcements, support replies. "CFO" reads cold and corporate to a Vietnamese mass-affluent user and undercuts the warm Bé Tiền persona.
>
> When talking to users, position Bé Tiền as **người đồng hành quản lý tài sản** (companion that helps manage assets). The reviewer enforces this on every user-facing change.

---

## 🎯 Vision Statement (V3 — Refined)

**Xây dựng Personal CFO đầu tiên cho mass affluent Việt Nam — không chỉ tracking, mà giúp user nhìn thấy tương lai tài chính của mình và optimize đường đi.** *(internal positioning — see the rule above for customer-facing language)*

Không compete với Money Lover, MISA, Spendee. Không compete với Finhay, Tikop. Tạo ra category mới ở VN: **"Personal Financial Future Vision"** — kết hợp tracking + AI agent + predictive twin.

---

## 🔑 The Differentiator — Financial Twin

> **Đây là wow-factor sản phẩm, được agreed trong strategic review tháng 5/2026.**

> **Cập nhật (rev 2026-05-29 — strategic review "5 phút đầu"):** Twin vẫn là
> **differentiator + payoff** dài hạn. Nhưng review phát hiện Twin là feature
> *lean-forward* tuần-2 — nó chỉ xuất hiện SAU bước nhập tài sản (ma sát cao nhất),
> nên người mới rời đi trước khi chạm tới. Giải pháp ban đầu là **The Reading** —
> một WOW phút-1 chạy trên *zero data* ("Để em đoán thử về anh/chị…").
>
> **🛑 Đính chính (29/05/2026, sau khi triển khai & trải nghiệm thật): The Reading
> đã được GỠ BỎ.** Reading v0+v1 phản tác dụng: (1) vướng nút demo ở bước tài sản,
> (2) chuyển cảnh sang Twin gập ghềnh, (3) v0 đoán-trên-zero-data nghe generic/bói
> toán → hại uy tín một sản phẩm tài chính. Thay vào đó onboarding đi **thẳng**
> goal → asset → Twin, với `step_2_asset.asset_ack` bắc cầu mượt một nhịp vào Twin
> reveal. Cách kéo người mới tới Twin nay dựa vào việc **giảm ma sát + chuyển cảnh
> liền mạch**, không phải thêm một màn đoán. WOW #0 (xưng hô) và WOW #3 (nhắn chủ
> động) vẫn giữ. Chi tiết: banner DECISION trong
> [`phase-4.4/phase-4.4-detailed.md`](phase-4.4/phase-4.4-detailed.md).

**Bé Tiền của bạn năm 2030 sẽ thế nào?**

Visual avatar/dashboard show financial future based on current trajectory. Updates daily based on actions. Compare:
- **Current trajectory** (do nothing different)
- **Optimal trajectory** (recommended actions)
- **Alternate scenarios** ("nếu tăng tiết kiệm 10%", "nếu mua nhà bây giờ")

### Why Twin = Wow Factor

1. **Vietnam-specific gap** — không có sản phẩm VN nào làm
2. **Mass Affluent psyche match** — họ obsess về future ("tài sản con cháu", "an nhàn hưu trí")
3. **Shareable** — visualization của twin có thể viral trên FB/Zalo
4. **Sticky** — user check twin daily như check Strava/Fitbit avatar
5. **Justifies premium pricing** — "đây là crystal ball cho tài chính của bạn"
6. **Leverages existing tech** — Phase 3.7 agent có thể compute projections

### Critical Framing Decision

**KHÔNG hiển thị single number predictions** — sẽ lose trust khi sai.

**HIỂN THỊ probability cones:**
> "Trên trajectory hiện tại, tài sản 2030 của bạn có thể nằm trong khoảng:
> 📊 Conservative: 3.5 tỷ
> 📈 Likely: 5.2 tỷ
> 🚀 Optimistic: 7.8 tỷ
> 
> Phụ thuộc vào market performance + savings rate."

**Mỗi 6 tháng:** Update + show "predictions vs actual" chart để build trust qua transparency.

---

## 💰 Pricing Strategy V3 (Adjusted Down)

**Strategic shift:** Volume play thay vì premium niche.

| Tier | Price | Position | Mental Anchor |
|------|-------|----------|---------------|
| **Free** | 0đ | Hook + onboarding | Spotify Free |
| **Pro** | **68k/tháng** | Mass appeal | 2 ly cafe |
| **CFO** | **168k/tháng** | Premium volume | < Spotify Family (199k) |

### Why Pricing Pivot

| Original (149k/399k) | New (68k/168k) | Implication |
|----------------------|----------------|-------------|
| Premium niche | Mass affluent volume | Need 6-7x users for same revenue |
| Compete với advisor (10-20tr) | Compete với streaming services | Different mental category |
| Must-have product | Nice-to-have OK | Less pressure on every feature |
| LTV high, CAC justify | LTV moderate, CAC strict | Marketing efficiency critical |

### Cost Analysis at 68k Pro

- Phase 3.7 agent cost: ~$0.0006/query average
- Heavy user (~500 queries/month) = ~$0.30 cost
- 68k - $0.3 USD = **~$2.7 USD profit margin per heavy user**
- Existing rate limits (10 Tier 3/hour, 100 total/hour) compatible

→ Pricing economically viable. CFO tier (168k) cho power users + special features.

---

## 👥 Target User — Refined

5-level ladder (2026 rescale), **focus chính: Level 1-2 (Young Pro + Mass Affluent)**:

- **Level 0 (Starter, 0-30tr):** Free tier, low priority for marketing
- **Level 1 (Young Pro, 30-300tr):** Pro target, biggest growth segment
- **Level 2 (Mass Affluent, 300tr-3 tỷ):** Trợ lý Tài sản target, highest LTV
- **Level 3 (HNW, 3 tỷ - 30 tỷ):** Trợ lý Tài sản target, white-glove acquisition
- **Level 4 (Đỉnh Cao, 30 tỷ+):** Multi-generational, family-office mindset, preservation-first

Twin appeals MOST to Level 1-2 — họ đang **building** tài sản → Twin show "trajectory đẹp" có ý nghĩa.

---

## 🏛️ 3 Trụ Cột (Updated)

### Trụ Cột 1: Wealth Tracking & Management ✅ DONE
- Cash, stocks, BĐS, crypto, vàng (Phase 3A) ✅
- Multi-asset portfolio view (Phase 3A) ✅
- AI agent queries (Phase 3.7) ✅
- Rental property, multi-income tracking (Phase 3.8) ✅

### Trụ Cột 2: Cashflow Intelligence ✅ DONE
- Basic income/expense (Phase 3A) ✅
- Threshold-based capture (Phase 3A) ✅
- AI agent for queries (Phase 3.7) ✅
- Recurring transactions, forecasting v1 (Phase 3.8) ✅
- Cashflow forecasting v2 + low-balance alerts (Phase 4B) ✅

### Trụ Cột 3: Investment Intelligence ✅ DONE
- Real-time market data (Phase 3.9 SSI/VNDIRECT/CoinGecko/SJC) ✅
- AI advisory (Phase 3.7 Tier 3) ✅
- Twin projections (Phase 4A/4B) ✅

### Trụ Cột 4: Future Vision ✅ DONE (THE DIFFERENTIATOR)
- Financial Twin với probability cones (Phase 4A) ✅
- Trajectory comparison (current vs optimal) (Phase 4A) ✅
- Daily twin updates (Phase 4A) ✅
- Life event simulation (Phase 4B) ✅
- **Operator monitoring** layer (Phase 4.2.5) ✅ để track Twin engagement với cohort
- **Twin habit loop + weather metaphor** (Phase 4.3) ✅ — Twin từ feature khó hiểu → habit-forming experience (Khiêm tốn/Bình thường/Lạc quan thay P10/P50/P90, story-first narrative, on-demand recompute, Twin admin dashboard)

### Trụ Cột 5 (Operational): Customer Experience & Trust ✅ DONE
- Onboarding 3-step + first-Twin shortcut (Phase 4.1) ✅
- Trust card + financial data integrity (Phase 4.2 Epic 1) ✅
- Next Best Action 9-CTA matrix + briefing quality (Phase 4.2 Epic 2) ✅
- Day 7 positioning micro-survey (Phase 4.2 Epic 3) ✅

---

## 📋 Roadmap V3 — Path to Tết 2027

> **Implementation velocity:** 3-4 ngày/phase (với Claude Code support). Test/polish slower → realistic ~2 tuần/phase. Buffer included.

### MAY-JUNE 2026 — Foundation Complete

#### ✅ Phase 1: UX Foundation — DONE
- 3 tuần, telegram bot foundation

#### ✅ Phase 2: Personality & Care — DONE
- Bé Tiền persona, onboarding

#### ✅ Phase 3A: Wealth Foundation — DONE
- 4 tuần, asset model + net worth + briefing

#### ✅ Phase 3.5: Intent Understanding Layer — DONE
- 3 tuần, intent classifier + advisory + voice

#### ✅ Phase 3.6: Menu UX Revamp — DONE
- 1.5 tuần, 5-category menu + adaptive

#### ✅ Phase 3.7: Agent Architecture — DONE (just shipped)
- 3 tuần, 3-tier orchestrator + 5 tools + streaming

#### ✅ Phase 3.8: Wealth Completion — DONE
**Duration:** ~2 tuần | **Shipped:** Early May 2026

5 Components shipped:
1. Rental property tracking (Case A — chủ nhà cho thuê)
2. Multi-income streams (6 types)
3. Recurring transactions + reminders (user explicit ask)
4. Cashflow forecasting Simple v1
5. Goals management complete (7 templates)

#### 🔥 Phase 3.8.5: Pre-Launch Readiness — STARTING NOW
**Duration:** ~3-4 ngày | **Target ship:** Mid-May 2026 | **Inserted:** May 2026 (post-3.8)

2 Components để chuẩn bị soft launch tháng 6:

1. **Feedback System (passive only):**
   - `/feedback` command — free-form text only (zero friction)
   - Backend auto-classification (LLM-based: bug/suggestion/praise/etc.)
   - Active prompts strict (4-6/year max, post-major-events)
   - Storage with full context (user state, version, recent actions)

2. **User Profile Minimal (auto-derived):**
   - Profile view với auto-derived stats (account age, wealth level VN, asset diversity, tracking streak)
   - Editable: display name, age range (optional), notification prefs
   - **Wealth Level mapping (Vietnamese, 2026 rescale):**
     - Khởi Đầu (0-30tr) 🌱
     - Trẻ Năng Động (30-300tr) 🚀
     - Trung Lưu Vững (300tr-3 tỷ) 💎
     - Tinh Hoa (3 tỷ - 30 tỷ) 🏆
     - Đỉnh Cao (30 tỷ+) 👑

**Out of scope (deferred):**
- ❌ Wealth Badge → Phase 4.5 (sau Twin để có context richer)
- ❌ Achievement system → Phase 4.5
- ❌ Share images → Phase 4.5 (note: badges fully private — không share công khai)

### JUNE 2026 — Soft Launch

#### Phase 3.9: Market Data Real — ✅ DONE
**Shipped:** 2026-05-08

- SSI/VNDIRECT integration (stocks)
- CoinGecko (crypto)
- SJC scraping (gold)
- Bank rate aggregator
- Replace Phase 3.7 market data stubs

#### Phase 3.9.5: Pre-Launch UX Polish — ✅ DONE
**Shipped:** 2026-05-11

- 11 dogfooding fixes (Wealth/Dashboard/Cashflow/Market menus)
- 2 menu renames + Telegram animation emoji upgrade
- Clean foundation cho soft launch

#### Phase 4A: Financial Twin Conservative MVP — ✅ DONE
**Shipped:** 2026-05-11

- Monte Carlo probability cones (P10/P50/P90)
- Current vs Optimal trajectory
- Telegram + Mini App basic surface
- Weekly cron + daily snapshot delta
- Channel-agnostic foundation

#### Phase 4B: Twin Polish + Life Events + Cashflow v2 + Zalo — ✅ DONE
**Shipped:** 2026-05-12

- Life Event Simulator (mua nhà/kết hôn/con cái injected into MC paths)
- Cashflow Forecasting v2 (auto-detect recurring + low-balance alerts)
- Twin UX polish
- Zalo OA adapter foundation (deferred activation to Phase 5.x)

#### Phase 4.1: Pre-Launch Hardening — ✅ DONE
**Shipped:** 2026-05-13

- Onboarding 3-step + first-Twin shortcut
- Cost guardrail per user
- Sentry + KPI digest + feedback triage SLA
- Shareable Twin image
- Predictions-vs-actual calibration
- 50-user soft launch playbook

#### Phase 4.2: Customer Experience Hardening — ✅ DONE
**Shipped:** 2026-05-13

CX-ready bridge giữa engineering readiness và cohort expansion:
- Epic 1: Trust card + financial data integrity guardrails
- Epic 2: Next Best Action 9-CTA matrix + briefing content quality + query-first prompts
- Epic 3: Day 7 positioning micro-survey + kill criterion update
- 7 stories + 3 migrations + 3 deploy tasks

#### Phase 4.2.5: Admin Observability — ✅ DONE
**Shipped:** 2026-05-26 | **Duration:** ~3 tuần

Admin dashboard (React + Vite + FastAPI) cho operator/founder monitor soft launch:
- KPI hero (DAU/MAU/stickiness/cost per user)
- 6 charts: User growth, DAU, feature clicks, intent breakdown, tier distribution, cohort retention
- User directory với search/filter/PII mask + audit log
- JWT auth với force-password-change first login
- License data model placeholder (activate ở Phase 5.7 cùng Pro launch)
- 23 stories / 7 Epics / ~66 SP
- Inserted để không phải query DB tay khi cohort scale 50 → 500

#### Phase 4.3: Twin Enhancement + Habit Loop + Admin Dashboard — ✅ DONE
**Shipped:** 2026-05-29 | **Duration:** ~3 tuần

Twin từ feature khó hiểu → habit-forming experience (4 Epics / 15 stories):
- **Epic 1 — Comprehension:** weather metaphor (🌧️ Khiêm tốn / ⛅ Bình thường / ☀️ Lạc quan) thay P10/P50/P90, life-outcome translation
- **Epic 2 — Story-first narrative:** 4-5 màn swipe story + mascot personification thay vì bày số liệu
- **Epic 3 — Habit loop:** on-demand recompute (<5s) + causality + action prompt + negative delta handling + delta threshold + return tease
- **Epic 4 — Twin admin dashboard:** engagement funnel, loop health, comprehension, delta distribution (4 sections)
- **Roadmap impact:** Phase 5.0 (Encryption) lùi ~3 tuần; timeline soft launch tháng 6/2026 vẫn an toàn.

#### Phase 4.4: First-5-Minutes WOW — 📋 PLANNED (current)
**Mục tiêu:** WOW phút-0 cho người mới — hook kéo tới Twin, **không thay** Twin.

Chẩn đoán review "5 phút đầu": sản phẩm không thiếu feature, thiếu *5 phút đầu*.
Twin (differentiator) bị backloaded sau bước nhập tài sản → người mới rời trước khi
chạm. Phase 4.4 giảm ma sát & làm mượt đường tới Twin (3 Epics còn hiệu lực,
Epic 1 The Reading đã gỡ — xem dưới):
- **WOW #0 — Salutation:** thêm cột `users.salutation`, hỏi anh/chị/bạn trong onboarding (gộp với bước tên). Cho Bé Tiền xưng hô ấm (anh/chị) ở mọi surface có giọng nói.
- ~~**WOW #1 — The Reading ⭐**~~ — 🛑 **GỠ BỎ (29/05/2026).** Màn "đoán thử trên zero data" phản tác dụng (vướng nút demo, chuyển cảnh gập ghềnh, generic → hại uy tín). Thay bằng chuyển cảnh liền mạch goal → asset → Twin (`step_2_asset.asset_ack`). Chi tiết: banner DECISION trong `phase-4.4/phase-4.4-detailed.md`.
- **WOW #2 — Screenshot onboarding:** chụp app ngân hàng → OCR số dư → net worth ~30s (tái dùng pipeline OCR, không gọi Claude vision). Rủi ro cao nhất, cắt được nếu trượt T6.
- **WOW #3 — Proactive companion:** thêm trigger vào `empathy_engine` đã chạy hourly — Bé Tiền nhắn trước một cách ấm.
- **Twin positioning:** Twin vẫn là payoff (phút 4); đường tới Twin nay dựa vào giảm ma sát + chuyển cảnh mượt, không phải màn đoán phút-1.
- **Roadmap impact:** Phase 5.0 (Encryption) lùi thêm ~1-1.5 tuần; soft launch tháng 6/2026 vẫn an toàn.
Detail: [`phase-4.4/phase-4.4-detailed.md`](phase-4.4/phase-4.4-detailed.md).

**🎉 Tháng 6 SOFT LAUNCH** với foundation complete:
- 50 founding member (50% lifetime discount khi Pro ra mắt — commitment honored)
- Admin dashboard monitor sức khỏe sản phẩm
- Feedback collection (Phase 3.8.5) + Day 7 micro-survey (Phase 4.2)
- Bug fixes + content polish
- Begin building user base for cohort data later

### JULY-AUGUST 2026 — Encryption + Zalo Rollout

> **Note (rev 2026-05-13):** Phase 4A/4B đã ship sớm hơn dự kiến (mid-May, không phải July). Twin polish + Life Events đã merge vào Phase 4B. Roadmap July–August giờ tập trung vào encryption infra + Zalo channel expansion.

#### Phase 5.0: Encryption End-to-End
**Duration:** ~2-3 tuần | **Target ship:** Late July 2026

- Encryption infrastructure (at-rest + in-transit hardening)
- **KHÔNG expose user-facing** trong trust copy (PM decision: tránh confuse user về commitment chưa hoàn thiện)
- Foundation cho future trust-and-safety improvements
- Operator editorial discipline (Phase 4.2 D.1) vẫn áp dụng cho đến khi encryption fully shipped

#### Phase 5.1–5.3: Zalo Channel Rollout
**Duration:** ~4-6 tuần | **Target ship:** Mid August – Mid September 2026

- **5.1 Zalo Spike & OA Verification**: Verified business account, webhook + adapter spike, validate 300-char limit
- **5.2 Zalo Core Product Parity**: Toàn bộ product hiện tại lên Zalo (intent classifier, asset entry, Twin view, briefing, advisory)
- **5.3 Zalo Mini App**: Mini App equivalent của Telegram Mini App (Twin dashboard, portfolio view)
- Channel strategy: full-parity với Telegram (corrected từ Mini App-only proposal)
- 48h window engagement design

### SEPTEMBER-NOVEMBER 2026 — Behavioral & Social

#### Phase 5.4: Achievement & Badges (Private)
**Duration:** ~1-2 tuần | **Target ship:** Mid September 2026

- Wealth milestone badges (lần đầu net worth +10%, lần đầu Twin within band 3 lần liên tiếp, streak briefing)
- Wealth Level badges (Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa)
- Streak tracking, growth markers, personal celebrations với Twin context
- **Private only — no social sharing / leaderboard** (Vietnamese mass affluent culture is "kín tiếng về tiền")

**Why private:** Public wealth display creates fraud risk + comparison anxiety. Gamification through personal achievement, not social validation.

#### Phase 5.5: Behavioral Engine
**Duration:** ~2-3 tuần | **Target ship:** Late September 2026

- Anomaly detection (pattern breaks)
- Personalized nudges (wealth-aware)
- **Synthetic cohort data** (not real peer yet)
- Financial DNA profile (spend patterns + risk tolerance)
- Chạy sau ≥ 2 tháng real data

**Critical:** Real peer data requires user base. Synthetic placeholder until data đủ.

#### Phase 5.6: Household Mode
**Duration:** ~2 tuần | **Target ship:** Mid October 2026

- Multi-user household: shared assets, joint goals
- Privacy boundaries (mỗi thành viên có view riêng)
- Couple Twin
- **Match Mass Affluent target** (most have spouses)

### NOVEMBER-DECEMBER 2026 — Pre-Tết Polish

#### Phase 5.7: Monetization Infrastructure
**Duration:** ~3 tuần | **Target ship:** November 2026

- License management activated (Phase 4.2.5 placeholder → full implementation)
- Plan tiers: Free / Pro (68k) / CFO (168k) với feature gates
- **Founding 50 honors 50% lifetime discount** (Phase 4.1 commitment)
- Payment integration: VNPay/MoMo/ZaloPay (VN-first)
- Revenue metrics: MRR, ARR, churn, LTV, ARPU, CAC
- Trial conversion funnel + churn risk scoring

#### Tết Special Features
**Duration:** ~3 tuần | **Target ship:** Mid December 2026

- Lì xì tracker
- Twin year-end review
- "Tài sản 2027 của bạn" framing
- Viral share images
- Tết-themed UI elements

### JANUARY-FEBRUARY 2027 — TẾT BÙNG NỔ 🎆

#### Phase 6.0: Tết Launch (Public)
**Duration:** Ongoing

- **Pricing tiers go live:** Free + Pro 68k + CFO 168k (gated by Phase 5.7)
- **Zalo là primary channel, Telegram secondary** (matched cohort distribution)
- Influencer partnerships
- **Real peer data activated** (đủ users by now)
- Marketing campaign full force
- Public PR moments (TechCrunch VN, etc.)

### MARCH 2027+ — Scale Phase

#### Phase 7+: Scale Infrastructure
- Native mobile app (only when PMF proven: Pro conversion ≥ 3%, DAU ≥ 40%)
- PWA web dashboard
- Cashflow forecasting v3 (ML-based)
- Multi-region (TBD)
- Advanced features based on real usage data

> **Carry-forward commitments** (xem `docs/current/phase-4.2/master-roadmap.md` section "Carry-Forward Commitments" cho full list — founding 50 discount, trust card commitment, Zalo full-parity, operator editorial discipline).

---

## 🛤️ Cashflow Forecasting Roadmap

Special note vì user requested guidance:

| Version | Method | When | Why |
|---------|--------|------|-----|
| **v1: Simple** | Average last 3 months | Phase 3.8 | Reliable baseline, no data requirements |
| **v2: Pattern** | Detect recurring + manual events | Phase 4B (with Twin) | Twin needs better forecasts |
| **v3: ML-based** | Trend prediction model | Phase 8+ post-Tết | Need 6+ months data to train |

**Logic:** Each version requires more data. Start simple, evolve as user base + data grows.

---

## ⚠️ Risk Matrix V3

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Twin predictions inaccurate at launch | Medium | High | Probability cones + transparency framing |
| Peer data insufficient for Tết launch | Medium | Medium | Synthetic cohort fallback ready |
| User base growth slower than expected | High | High | Soft launch June + iterate before Tết |
| Implementation slip beyond Tết | Low | High | 3-4 day/phase velocity, buffer in roadmap |
| Pricing too low for revenue targets | Medium | Medium | Volume strategy, can add CFO+ tier later |
| Competitive response (MISA/Money Lover add AI) | Medium | Medium | Twin moat unique, hard to replicate fast |

---

## 🎯 Success Metrics V3

### Pre-Launch (Tháng 6 Soft Launch)
- Phase 3.7 agent ≥90% query success
- Phase 3.8 features all functional
- 50+ early users by end of June

### Pre-Tết (October-December)
- ≥1000 active users
- Twin engagement: ≥40% daily check
- Net worth tracked >500tr average per user

### Tết 2027 Launch
- Pricing conversion: 5-10% Free→Pro
- Pro→CFO upsell: 10-15%
- D7/D30 retention: 70%/50%
- NPS: ≥50

### Year 1 Post-Tết
- 10K+ active users
- ARR: 5-10 tỷ VND
- Public PR moments (TechCrunch VN, etc.)

---

## 🎨 Guiding Principles V3 (Updated)

1. **Wealth-first, expense-second** — Net worth là North Star (carried from V2)
2. **Future-vision distinguishes** — Twin = differentiator, not nice-to-have
3. **Probability over precision** — Frame predictions honestly, build trust
4. **Foundation before flash** — Complete data before wow features (Phase 3.8 before 4A)
5. **Volume + Premium** — 68k for mass, 168k for power users (not premium-only)
6. **Vietnam-specific moments** — Tết, lễ Tết, văn hóa Việt
7. **Ship fast, iterate** — 3-4 days/phase với Claude Code, no perfectionism
8. **Trust through transparency** — Show predictions vs actuals, admit uncertainty

---

## 📝 Strategic Decisions Log (V3 Session)

Following decisions made during strategic review (May 2026):

1. **Path Y selected** — Differentiation over incremental improvement
2. **Twin = wow factor** — Phased: Conservative MVP → Polish → Life Sim
3. **Pricing pivot** — 149/399 → 68/168 (volume play)
4. **Timeline** — June 2026 soft launch, Tết 2027 explosion
5. **Phase 3.8 scope** — All 5 components in single phase
6. **Rental tracking** — Case A only (chủ nhà), Case B = recurring expense
7. **Cashflow forecast** — Simple v1 → Pattern v2 → ML v3 progression
8. **Goals** — Templates first (Câu 4: c), single-goal focus (Câu 4: a)
9. **Peer benchmarking** — Synthetic data initially, real after user base grows
10. **Household mode** — Move earlier (Phase 6) to match Mass Affluent target

### Phase 3.8.5 Insertion (May 2026, post-Phase 3.8)

**Decision:** Insert Phase 3.8.5 (Pre-Launch Readiness) between Phase 3.8 và Phase 3.9.

**Reason:** Pre-soft-launch (June 2026) cần 2 critical features:
- Feedback channel để collect early user signals
- User profile để hỗ trợ user identity (xem/edit thông tin)

**Scope decisions:**
- Feedback: passive only, free-form text, backend auto-classification (zero friction)
- Profile: minimal, auto-derived stats, anti-form philosophy
- Wealth Level mapping (Vietnamese): Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa
- Wealth Badge: **fully private** — no social sharing (Vietnamese cultural fit)
- Achievement system: **deferred to Phase 4.5** (sau Twin để có context richer)

**Impact analysis:**
- Timeline: +3-4 ngày (3.8.5 work) + ~1-2 tuần (Phase 4.5 added) = ~+1.5 tuần total
- Tết 2027 target: **vẫn safe** (buffer trong roadmap)
- Risk: minimal — additive, not disruptive

**New Phase 4.5 added:** Achievement System + Wealth Badges (Private), inserted between Phase 4B và Phase 5.

### Phase 4.2.5 Insertion (May 2026, post-Phase-4.2)

**Decision:** Insert Phase 4.2.5 (Admin Observability Layer) giữa Phase 4.2 và Phase 5.0.

**Reason:** Soft launch 50 founding member (June 2026) cần operator dashboard để monitor sức khỏe sản phẩm — không thể tiếp tục query DB tay khi cohort scale 50 → 500. Phase 4.2 đã ship Day 7 micro-survey + NBA matrix + briefing content quality, nhưng signals từ những work này cần một surface để đọc.

**Scope:**
- 7 Epics, 23 stories, ~3 sprints
- React + Vite frontend với "financial editorial" aesthetic (không "AI slop dashboard")
- FastAPI namespace `/api/admin/*`
- JWT auth + force-password-change first login
- 6 KPI cards + 6 charts (growth, DAU, intent breakdown, tier distribution, feature clicks, cohort retention)
- User directory với PII mask + audit log
- License data model placeholder cho Phase 5.7 (Pro launch)
- **No test-cases file** — test scenarios inline trong từng story; smoke test checklist trong Epic 6.3

**Naming history:** Originally drafted dưới tên "Phase 3.6 Admin Dashboard" (docs/current/AdminDashboard/) — renamed Phase 4.2.5 vì 3.6 đã được Menu UX Revamp dùng và shipped 2026-05-05.

**Story 1.5 bridge migration removed:** Phase 3.5 (Intent Layer) đã ship `messages.resolved_by` column từ 2026-05-02 — original bridge migration không còn cần thiết.

**Roadmap impact:**
- Phase 4.1 ✅ Done, Phase 4.2 ✅ Done.
- Soft launch tháng 6 vẫn safe (3-tuần dev buffer trong roadmap).
- Phase 5.0 (Encryption) push back ~3 tuần.
- License placeholder ship sớm tránh migration đau đầu khi Phase 5.7 activate Pro tier.

### Phase 4.3 Insertion (May 2026, post-Phase-4.2.5)

**Decision:** Insert Phase 4.3 (Twin Enhancement + Habit Loop + Admin Dashboard) giữa Phase 4.2.5 và Phase 5.0.

**Reason:** Financial Twin là *the differentiator* nhưng probability cone (P10/P50/P90) quá khó hiểu với mass-affluent user — risk là wow-factor không convert thành habit. Trước soft launch tháng 6 cần biến Twin từ feature "đọc một lần rồi thôi" → trải nghiệm kéo người dùng quay lại hàng tuần.

**Scope:**
- 4 Epics, 15 stories, ~3 tuần
- Epic 1 — Comprehension: weather metaphor (🌧️ Khiêm tốn / ⛅ Bình thường / ☀️ Lạc quan) thay P10/P50/P90 + life-outcome translation
- Epic 2 — Story-first narrative: 4-5 màn swipe story + mascot personification
- Epic 3 — Habit loop: on-demand recompute (<5s) + causality + action prompt + negative delta + delta threshold + return tease
- Epic 4 — Twin admin dashboard: engagement funnel, loop health, comprehension, delta distribution (4 sections)

**Roadmap impact:**
- Phase 4.2.5 ✅ Done (2026-05-26), Phase 4.3 ✅ Done (2026-05-29).
- Phase 5.0 (Encryption) lùi thêm ~3 tuần.
- Soft launch tháng 6/2026 vẫn an toàn — habit loop chính là leverage cho cohort retention từ ngày đầu.

---

## 📝 Changelog

**V3 (current):** Post-Phase 3.7 strategic review (May 2026)
- Added Financial Twin as primary differentiator
- Pricing adjusted down (volume strategy: 149/399 → 68/168)
- Roadmap restructured với Tết 2027 target
- Phase 3B/4/5/6 substantially redefined
- Cashflow forecasting roadmap added (v1 → v2 → v3 progression)
- Pivot rationale documented in [MIGRATION_NOTES_V2_V3.md](../archive/MIGRATION_NOTES_V2_V3.md)
- **2026-05-29:** Phase 4.2.5 (Admin Observability) ✅ + Phase 4.3 (Twin Enhancement + Habit Loop) ✅ shipped. Next focus: Phase 5.0 (Encryption End-to-End) sau soft launch tháng 6.

**V2:** [archived](../archive/strategy-v2.md) — Pivot to Personal CFO positioning (wealth-first instead of expense-first)

**V1:** [archived](../archive/strategy-v1.md) — Original "Finance Assistant" strategy (expense tracking focus)

> **Note for future-Phuong:** Khi tạo V4, follow same pattern: archive current strategy.md → strategy-v3.md, create MIGRATION_NOTES_V3_TO_V4.md, never delete.

---

**Tết 2027 = launch moment. From here forward, every decision optimizes for that moment. 🎆💚🚀**
