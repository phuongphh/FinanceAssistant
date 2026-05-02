# Personal CFO Assistant — Documentation

> **Vision:** Xây dựng Personal CFO đầu tiên cho tầng lớp trung lưu Việt Nam — AI assistant không chỉ theo dõi chi tiêu, mà quản lý toàn bộ tài sản, tạo báo cáo hàng ngày và tư vấn đầu tư.

---

## 🎯 Current Focus

**✅ Phase 3.5 — Intent Understanding Layer** (3 tuần)

- 📖 Read: [current/phase-3.5-detailed.md](current/phase-3.5-detailed.md)
- 📋 Issues: [current/phase-3.5-issues.md](current/phase-3.5-issues.md)
- 📊 Perf report: [current/phase-3.5-perf-report.md](current/phase-3.5-perf-report.md)
- 🔍 Regression sign-off: [current/phase-3.5-regression-signoff.md](current/phase-3.5-regression-signoff.md)
- 🧪 User testing protocol: [current/phase-3.5-user-testing.md](current/phase-3.5-user-testing.md)
- 📈 Pattern improvement loop: [current/phase-3.5-improvement-process.md](current/phase-3.5-improvement-process.md)
- 📝 Retrospective: [current/phase-3.5-retrospective.md](current/phase-3.5-retrospective.md)

**Next up:** User testing (Story #133) → ship-or-iterate decision → Phase 3B.

---

## 📚 Navigation

### Strategy
- 📜 [Product Strategy V2](current/strategy.md) — Vision, roadmap, positioning, pricing
- 📝 [Migration Notes V1→V2](archive/MIGRATION_NOTES.md) — Tại sao pivot từ Finance Assistant → Personal CFO

### Implementation Guides

| Phase | Status | Detailed Doc | Issues |
|-------|--------|--------------|--------|
| Phase 1: UX Foundation | ✅ Complete | [phase-1-detailed.md](current/phase-1-detailed.md) | — |
| Phase 2: Personality & Care | ✅ Complete | [phase-2-detailed.md](current/phase-2-detailed.md) | — |
| Phase 3A: Wealth Foundation | ✅ Complete | [phase-3a-detailed.md](current/phase-3a-detailed.md) | [phase-3a-issues.md](current/phase-3a-issues.md) |
| **Phase 3.5: Intent Understanding** | ✅ **Complete** | **[phase-3.5-detailed.md](current/phase-3.5-detailed.md)** | **[phase-3.5-issues.md](current/phase-3.5-issues.md)** |
| Phase 3B: Market Intelligence | 🔮 Planned | [phase-3b-outline.md](current/phase-3b-outline.md) | TBD after 3.5 validation |
| Phase 4: Investment Intelligence | 🔮 Planned | TBD | TBD |
| Phase 5: Behavioral Engine | 🔮 Planned | TBD | TBD |
| Phase 6: Scale & Commercialize | 🔮 Planned | TBD | TBD |

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
