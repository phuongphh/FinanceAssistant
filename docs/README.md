# Personal CFO Assistant — Documentation

> **Vision:** Xây dựng Personal CFO đầu tiên cho tầng lớp trung lưu Việt Nam — AI assistant không chỉ theo dõi chi tiêu, mà quản lý toàn bộ tài sản, tạo báo cáo hàng ngày và tư vấn đầu tư.

---

## 🎯 Current Focus

<!-- BEGIN: phase-status:current-block -->
✅ **Phase 3.6 — Menu UX Revamp** (1.5 tuần)

- 📖 Detailed doc: [docs/current/phase-3.6-detailed.md](docs/current/phase-3.6-detailed.md)
- 📋 Issues: [docs/current/phase-3.6-issues.md](docs/current/phase-3.6-issues.md)
- 📝 Scope: Wealth-first 3-level menu, adaptive intros, hard cutover from V1 flat menu

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
| Phase 1: UX Foundation | ✅ done | 3 tuần | [phase-1-detailed.md](docs/current/phase-1-detailed.md) | Telegram bot + manual entry + monthly report + Notion dashboard |
| Phase 2: Personality & Care | ✅ done | 3 tuần | [phase-2-detailed.md](docs/current/phase-2-detailed.md) | Onboarding, Bé Tiền tone, milestone celebration, empathy engine |
| Phase 3A: Wealth Foundation | ✅ done | 4 tuần | [phase-3a-detailed.md](docs/current/phase-3a-detailed.md) | Asset model, net worth, morning briefing, Mini App dashboard |
| Phase 3.5: Intent Understanding Layer | ✅ done | 3 tuần | [phase-3.5-detailed.md](docs/current/phase-3.5-detailed.md) | Rule + LLM intent classifier, confirm/clarify, advisory, voice queries |
| **Phase 3.6: Menu UX Revamp** | ✅ done | 1.5 tuần | [phase-3.6-detailed.md](docs/current/phase-3.6-detailed.md) | Wealth-first 3-level menu, adaptive intros, hard cutover from V1 flat menu |
| Phase 3B: Market Intelligence | 📋 next | TBD | [phase-3b-outline.md](docs/current/phase-3b-outline.md) | Real market data, advisory deepening, portfolio analytics |
| Phase 4: Investment Intelligence | 🔮 planned | TBD | — | Investment Twin, scenario modeling, rental property tracking |
| Phase 5: Behavioral Engine | 🔮 planned | TBD | — | Wealth-aware nudges, Financial DNA, anomaly detection |
| Phase 6: Scale & Commercialize | 🔮 planned | TBD | — | Public beta, subscriptions, multi-region, household mode |
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
