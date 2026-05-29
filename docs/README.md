# Personal CFO Assistant — Documentation

> **Vision:** Xây dựng Personal CFO đầu tiên cho tầng lớp trung lưu Việt Nam — AI assistant không chỉ theo dõi chi tiêu, mà quản lý toàn bộ tài sản, tạo báo cáo hàng ngày và tư vấn đầu tư.

---

## 🎯 Current Focus

<!-- BEGIN: phase-status:current-block -->
📋 **Phase 5.0 — Encryption End-to-End** (~2-3 tuần)

- 📝 Scope: Encryption infrastructure improvement; trust copy hiện không mention user-facing để tránh confuse user về commitment chưa ship. Ship as infra, not as feature.
<!-- END: phase-status:current-block -->

**Auto-sync:** This block is regenerated from
[`current/phase-status.yaml`](current/phase-status.yaml). Edit that
file when phases change — never edit between the markers by hand.
The companion script lives at
[`../scripts/sync_phase_status.py`](../scripts/sync_phase_status.py)
and the GitHub Action `sync-phase-status.yml` runs on every push.

---

## 📚 Navigation

### Strategy
- 📜 [Product Strategy V2](current/strategy.md) — Vision, roadmap, positioning, pricing
- 📋 [Phase Status (source of truth)](current/phase-status.yaml) — Single YAML driving all roadmap tables in this repo
- 📝 [Migration Notes V1→V2](archive/MIGRATION_NOTES.md) — Tại sao pivot từ Finance Assistant → Personal CFO

### Implementation Guides

<!-- BEGIN: phase-status:roadmap-table -->
| Phase | Status | Duration | Detailed Doc | Description |
|---|---|---|---|---|
| UX Foundation | ✅ done | 3 tuần | [phase-1-detailed.md](docs/archive/phase-1-detailed.md) | Telegram bot + manual entry + monthly report + Notion dashboard |
| Personality & Care | ✅ done | 3 tuần | [phase-2-detailed.md](docs/archive/phase-2-detailed.md) | Onboarding, Bé Tiền tone, milestone celebration, empathy engine |
| Wealth Foundation | ✅ done | 4 tuần | [phase-3a-detailed.md](docs/archive/phase-3a-detailed.md) | Asset model, net worth, morning briefing, Mini App dashboard |
| Intent Understanding Layer | ✅ done | 3 tuần | [phase-3.5-detailed.md](docs/current/phase-3.5-detailed.md) | Rule + LLM intent classifier, confirm/clarify, advisory, voice queries |
| Menu UX Revamp | ✅ done | 1.5 tuần | [phase-3.6-detailed.md](docs/archive/phase-3.6-detailed.md) | Wealth-first 3-level menu, adaptive intros, hard cutover from V1 flat menu |
| Agent Architecture | ✅ done | 3 tuần | [phase-3.7-detailed.md](docs/current/phase-3.7-detailed.md) | Two-tier agent (DB-Agent + Premium Reasoning), tool-use, orchestrator routing |
| Wealth Completion | ✅ done | 2 tuần | [phase-3.8-detailed.md](docs/current/phase-3.8-detailed.md) | Goals system schema migration, FeasibilityBand enum, 6 readers updated for backwards compatibility |
| Pre-Launch Readiness | ✅ done | 3-4 ngày | [phase-3.8.5-detailed.md](docs/current/phase-3.8.5/phase-3.8.5-detailed.md) | Feedback system (/feedback command + DeepSeek classifier + active prompts) + User Profile (view-mode, wealth levels VN, auto-derived stats, edit flows) |
| Market Data Real | ✅ done | 3 tuần | [phase-3.9-detailed.md](docs/current/phase-3.9/phase-3.9-detailed.md) | Real market data integration: stock (SSI/VNDIRECT), crypto (CoinGecko), gold (SJC/PNJ), bank rates, RSS news — stubs replaced and quality gate complete |
| Pre-Launch UX Polish | ✅ done | 5-7 ngày | [phase-3.9.5-detailed.md](docs/current/phase-3.9.5/phase-3.9.5-detailed.md) | Pre-launch UX polish: 11 dogfooding fixes (Wealth/Dashboard/Cashflow/Market menus) + 2 menu renames + Telegram animation emoji upgrade. Inserted before Phase 4A để clean foundation cho soft launch tháng 6/2026. |
| Market Intelligence | 🔮 planned | TBD | [phase-3b-outline.md](docs/current/phase-3b-outline.md) | Real market data, advisory deepening, portfolio analytics |
| Financial Twin Conservative MVP | ✅ done | ~3 tuần | [phase-4A-detailed.md](docs/current/phase-4A/phase-4A-detailed.md) | Financial Twin MVP: Monte Carlo probability cones (P10/P50/P90), Current vs Optimal trajectory, Telegram + Mini App basic surface, weekly cron + daily snapshot delta, channel-agnostic foundation |
| Twin Polish + Life Events + Cashflow v2 + Zalo | ✅ done | ~4 tuần | [phase-4B-detailed.md](docs/current/phase-4B/phase-4B-detailed.md) | Life Event Simulator (mua nhà/kết hôn/con cái injected into MC paths), Cashflow Forecasting v2 (auto-detect recurring + low-balance alerts), Twin UX polish, Zalo OA adapter foundation |
| Pre-Launch Hardening | ✅ done | ~3 tuần | [phase-4.1-detailed.md](docs/current/phase-4.1/phase-4.1-detailed.md) | Onboarding 3-step + first-Twin shortcut, cost guardrail per user, Sentry + KPI digest + feedback triage SLA, shareable Twin image, predictions-vs-actual calibration, 50-user soft launch playbook (June 2026) |
| Customer Experience Hardening | ✅ done | ~2 tuần | [phase-4.2-detailed.md](docs/current/phase-4.2/phase-4.2-detailed.md) | CX-ready bridge: Trust card + financial data integrity, Next Best Action 9-CTA matrix + briefing content quality + query-first prompts, Day 7 positioning micro-survey + kill criterion update. 7 stories + 3 migrations + 3 deploy tasks. |
| Admin Observability | ✅ done | ~3 tuần | [phase-4.2.5-detailed.md](docs/current/phase-4.2.5/phase-4.2.5-detailed.md) | Admin dashboard (React + Vite + FastAPI) cho operator monitor soft launch: KPI hero, 6 charts (growth, DAU, intent breakdown, tier distribution, feature clicks, cohort retention), user directory với search/filter/PII mask, audit log, JWT auth + force_password_change, license placeholder cho Phase 5.7. 23 stories / 7 Epics / ~66 SP. Ship trước soft launch tháng 6/2026. |
| Twin Enhancement + Habit Loop + Admin Dashboard | ✅ done | ~3 tuần | [phase-4.3-detailed.md](docs/current/phase-4.3/phase-4.3-detailed.md) | Twin từ feature khó hiểu → habit-forming experience: weather metaphor (Khiêm tốn/Bình thường/Lạc quan) thay P10/P50/P90, life-outcome translation, story-first narrative (4-5 màn swipe), mascot personification, habit loop (on-demand recompute <5s + causality + action + negative delta + delta threshold + return tease), Twin admin dashboard 4 sections (engagement funnel, loop health, comprehension, delta distribution). 4 Epics / 15 stories. |
| Encryption End-to-End | 📋 next | ~2-3 tuần | — | Encryption infrastructure improvement; trust copy hiện không mention user-facing để tránh confuse user về commitment chưa ship. Ship as infra, not as feature. |
| Zalo Spike & OA Verification | 🔮 planned | TBD | — | Zalo OA verified business account, webhook + adapter spike, validate 300-char limit + no-Markdown constraints with real flows |
| Zalo Core Product Parity | 🔮 planned | TBD | — | Toàn bộ product hiện tại trên Zalo: intent classifier, asset entry, Twin view, briefing, advisory — content layer adapted for Zalo constraints |
| Zalo Mini App | 🔮 planned | TBD | — | Zalo Mini App equivalent của Telegram Mini App: Twin dashboard, portfolio view, interactive cone, initData verification trên Zalo SDK |
| Achievement & Badges | 🔮 planned | TBD | — | Wealth milestone badges (lần đầu net worth +10%, lần đầu Twin within band 3 lần liên tiếp, streak briefing) — private, không leaderboard |
| Behavioral Engine | 🔮 planned | TBD | — | Wealth-aware nudges, Financial DNA profile (spend patterns + risk tolerance), anomaly detection — chạy sau ≥ 2 tháng real data |
| Household Mode | 🔮 planned | TBD | — | Multi-user household: shared assets, joint goals, privacy boundaries (mỗi thành viên có view riêng), couple Twin |
| Monetization Infrastructure | 🔮 planned | TBD | — | License management, rate limit + tier enforcement (free/pro/cfo UI), payment integration (VN gateways: VNPay/MoMo/ZaloPay), reconciliation + invoice. Pricing re-validate sau khi infra sẵn sàng. |
| Tết Launch (Public) | 🔮 planned | TBD | — | Public launch tháng 2/2027 (Tết) — Zalo là primary channel, Telegram secondary. Marketing campaign, multi-region, public pricing live. |
<!-- END: phase-status:roadmap-table -->

### Archive
- 📦 [v1 Finance Assistant](archive/v1-finance-assistant/) — Original positioning before pivot
  - [strategy-v1.md](archive/v1-finance-assistant/strategy-v1.md)
  - [phase-3-detailed-v1.md](archive/v1-finance-assistant/phase-3-detailed-v1.md)

---

## 🗂️ Folder Structure

```
docs/
├── README.md                              ← You are here
├── current/                               ← Active documents
│   ├── strategy.md                        ← Source of truth
│   ├── phase-1-detailed.md
│   ├── phase-2-detailed.md
│   ├── phase-3a-detailed.md               ← Current focus
│   ├── phase-3a-issues.md                 ← GitHub-ready issues
│   └── phase-3b-outline.md
├── issues/                                ← Per-issue snapshots
│   ├── README.md                          ← Issues index + navigation
│   ├── active/                            ← Currently open issues
│   └── closed/
│       ├── INDEX.md                       ← issue# → phase → title
│       └── by-phase/
│           ├── pre-phase/                 ← V1 features
│           ├── phase-1/                   ← Phase 1 closed issues
│           └── phase-2/                   ← Phase 2 closed issues
└── archive/                               ← Historical (don't delete!)
    ├── MIGRATION_NOTES.md
    └── v1-finance-assistant/
        ├── strategy-v1.md
        └── phase-3-detailed-v1.md
```

---

## 🛠️ How to Use These Docs

### If you're starting development on Phase 3A:
1. Read [strategy.md](current/strategy.md) — understand positioning + target user
2. Read [phase-3a-detailed.md](current/phase-3a-detailed.md) — understand WHAT to build
3. Open [phase-3a-issues.md](current/phase-3a-issues.md) — pick first issue
4. Copy issue → GitHub → assign to yourself → start coding

### If you're using Claude Code to implement:
1. Share `phase-3a-detailed.md` with Claude Code as context
2. Point it to the specific issue from `phase-3a-issues.md`
3. Claude Code generates code following the spec
4. Review → commit → close issue

### If you pivot product again:
1. Create new `MIGRATION_NOTES_V2_V3.md`
2. Move old docs to `archive/v2-personal-cfo/`
3. Update this README
4. **Don't delete old files** — preserve history

---

## 📊 Key Metrics to Track

From Phase 1 onwards, track:

**Activation:**
- % user hoàn thành onboarding (target: >70%)
- Time to first asset entry (target: <10 phút)

**Engagement (critical for Phase 3A+):**
- Daily Morning Briefing open rate (target: >60%)
- Avg assets tracked per user (target: >3 loại)

**Retention:**
- D7 / D30 retention (target: 70% / 50%)

**Wealth-specific:**
- Average net worth tracked per user (tăng theo thời gian → signal trust)
- % users có asset ngoài cash (target: >40% sau 3 tháng)

---

## 🎯 North Star Metric

**Daily Active Net Worth Viewers** — số users mở app xem net worth mỗi ngày.

Đây là metric quan trọng nhất vì nó signal:
1. User trust app với financial data
2. Morning briefing đang hoạt động
3. Habit đã hình thành
4. LTV cao

Target: **>60% of registered users** check net worth hàng ngày sau 1 tháng.

---

## 🚨 Product Principles (Đừng Quên)

1. **Wealth-first, expense-second** — Net worth là North Star, expense là supporting
2. **Ladder design** — App adapt theo user level, không one-size-fits-all
3. **Empowerment, not shame** — Framing positive (tăng tài sản), không negative (hạn chế chi tiêu)
4. **AI-native, không AI-added** — Mọi feature design với LLM ở core
5. **VN-specific** — Hiểu thị trường, văn hóa, ngôn ngữ Việt
6. **Ship sớm, validate, iterate** — Phase độc lập có giá trị, không làm hết mới release

---

**Questions? Re-read the docs. Docs are the source of truth. 💚**
