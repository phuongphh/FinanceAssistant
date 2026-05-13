# Bé Tiền — Master Roadmap

> **Last updated:** 2026-05-13
> **Status:** Phase 4.1 đang testing, Phase 4.2 planning đã xong (docs/current/phase-4.2/)
> **Convention note:** Từ Phase 4.2 trở đi, Epic dùng numbered convention (Epic 1, 2, 3...) thay vì lettered (Epic A, B, C).

---

## 📊 Phase Status Overview

| Phase | Title | Status | Notes |
|---|---|---|---|
| 3A | Wealth Foundation | ✅ Done | Asset data models, morning briefing infra, storytelling expense capture, net worth viz |
| 3.5 | Intent Understanding Layer | ✅ Done | 5-layer pipeline: pre-filter → VN rule-based → LLM classifier → confidence dispatcher → personality composer |
| 3.9 | (existing phase) | ✅ Done | — |
| 4A | Financial Twin MVP | ✅ Done | Cone chart, P10/P50/P90, basic twin engine |
| 4B | Twin Polish + Life Events + Cashflow v2 + Zalo OA Adapter | ✅ Done | Life event simulator, cashflow modeling, Zalo OA adapter (defer activation) |
| **4.1** | **Pre-Launch Hardening** | 🟡 **Testing** | **Soft launch 50 user T6/2026; engineering readiness** |
| **4.2** | **Customer Experience Hardening** | 🔵 **Planning** | **NEW — bridge eng-ready → CX-ready trước khi expand cohort** |
| 5.0 | Encryption End-to-End | ⚪ Planned | Encryption infra; trust copy hiện không mention user-facing để tránh confuse |
| 5.1–5.3 | Zalo Channel Rollout | ⚪ Planned | Zalo OA full-parity với 48h window engagement design (corrected từ initial Mini App proposal) |
| 5.4 | Achievement / Badge System | ⚪ Planned | — |
| 5.7 | Monetization Infrastructure | ⚪ Planned | Pro 88k single-tier launch; founding 50% lifetime discount honored |
| 5.8+ | Max Tier Feature Gate | ⚪ Planned | Defer cho đến khi có data về Pro usage patterns |
| 6+ | Native Mobile App | ⚪ Planned | Chỉ khi PMF proven (Pro conversion ≥ 3%, DAU ≥ 40%) |

### Legend
- ✅ Done — shipped và stable trên production
- 🟡 In Progress — đang implement / testing
- 🔵 Planning — docs đã xong, chưa start dev
- ⚪ Planned — roadmapped, chưa scope chi tiết

---

## 🔄 Phase Sequence Changes (May 2026)

### What changed

**Insert Phase 4.2** giữa Phase 4.1 và Phase 5.x. Lý do: review Phase 4.1 detailed phát hiện 5 customer-experience gap (trust, data quality, activation, positioning, query-first UX) chưa đóng. Phase 4.1 quá nghiêng về engineering readiness.

**Add Phase 5.0 (Encryption End-to-End)** vào Phase 5 sequence trước khi Zalo rollout. Encryption không expose tới user qua trust copy (decision của PM: tránh confuse user về commitment chưa ship) — sẽ ship như infrastructure improvement.

**Push Phase 5.1+ back ~2 tuần** accordingly.

### Why insert vs merge into 4.1

Phase 4.1 đã implemented xong và đang testing. Merge 4.2 work vào 4.1 = re-test toàn bộ → risk regression. Tách phase = ship 4.1 sạch trước, 4.2 builds on top.

---

## 📅 Updated Timeline

```
T0 (Mid-May 2026)     │ Phase 4.1 testing & deploy
T+2w (Early June)     │ Phase 4.1 soft launch start (50 founding member)
T+3w (Mid-June)       │ Phase 4.1 D7 data signal, decide 4.2 kickoff
T+4w (Late June)      │ Phase 4.2 dev start
T+6w (Early July)     │ Phase 4.2 ship, founding cohort fully on 4.2
T+8w (Mid-July)       │ Phase 4.2 D7 positioning survey first signals
T+10w (Late July)     │ Phase 5.0 (Encryption) kickoff — infrastructure improvement
T+14w (Late August)   │ Phase 5.1 Zalo rollout planning
```

**Note:** Đây là estimate optimistic. Mỗi phase có buffer ±1 tuần.

---

## 🎯 Phase 4.2 — Quick Summary

**Goal:** Bridge engineering-ready → customer-experience-ready trước khi mở rộng cohort 50 → 500.

**3 Epics:**
1. **Epic 1 — Trust & Data Integrity** (2.5 ngày): Trust card + financial data quality guardrails
2. **Epic 2 — Activation & Engagement** (2 ngày): Next Best Action 9-CTA matrix + briefing content quality + query-first prompts
3. **Epic 3 — Positioning Validation** (0.5 ngày): Day 7 micro-survey + kill criterion update

**Total:** 7 stories + 3 migrations + 3 deploy tasks = 16 issues, ~6.5 ngày work + buffer = ~2 tuần.

**Key files:**
- `docs/current/phase-4.2/phase-4.2-detailed.md` — master plan
- `docs/current/phase-4.2/phase-4.2-issues.md` — GitHub issue source
- `docs/current/phase-4.2/phase-4.2-test-cases.md` — manual test plan (~60-80 TCs trong batches 20)
- `docs/current/phase-4.2/phase-4.2-deploy-announcements.md` — deploy comms

---

## 📌 Carry-Forward Commitments (từ Phase 4.1 vào 4.2 và sau)

Đây là những promise/commitment đã được set ở Phase 4.1 hoặc 4.2 mà các phase sau phải honor:

1. **Founding 50 member — 50% lifetime discount khi Pro ra mắt**
   - Set in: Phase 4.1 C.4 founding_promise.md
   - Honor by: Phase 5.7 Monetization
   - Status: Schema ready (`founding_member_service.compute_discount`)

2. **Trust card commitment — "Chỉ bạn thấy chi tiết tài sản, không user nào khác"**
   - Set in: Phase 4.2 Story 1.1 trust_card.yaml
   - True with respect to: other users (cohort, public)
   - **Internal caveat:** founder/operator có thể query DB. Operator có editorial discipline (xem item 4) cho đến khi encryption ship Phase 5.0.
   - Note: user-facing trust copy KHÔNG mention encryption — tránh confuse với commitment chưa ship

3. **Zalo channel — full parity với Telegram**
   - Set in: Phase 4.1 detailed channel strategy section
   - Honor by: Phase 5.1-5.3 Zalo Rollout
   - Status: Design known (48h window engagement); audit Phase 4B adapter needed

4. **Operator editorial discipline — không reference số tiền user trong feedback reply**
   - Set in: Phase 4.2 D.1 operator-editorial-discipline.md
   - Honor by: ongoing — until encryption ships in Phase 5.0
   - Status: Doc created, checklist in daily check-in

---

## 🚫 Deferred / Killed Items

Items được scope ra khỏi current roadmap:

- ❌ **A/B testing framework** — quá heavy cho cohort < 200 user
- ❌ **OCR data quality check** (Claude Vision pipeline) — Phase 5.x
- ❌ **Multi-language EN/VN** — out of scope, VN primary
- ❌ **Social leaderboard / friend share** — Vietnamese cultural fit nói KHÔNG
- ❌ **Anonymized analytics export self-serve** — operator query DB trực tiếp
- ❌ **Mini App architecture cho Zalo** — corrected to full OA adapter (cheaper)

---

## 📝 Update Log

| Date | Change | Author |
|---|---|---|
| 2026-05-13 | Encryption moved Phase 4.3 → Phase 5.0; bỏ user-facing encryption commitment khỏi trust copy (PM decision: tránh confuse user) | PM |
| 2026-05-13 | Inserted Phase 4.2 (CX Hardening) after Phase 4.1 review | PM |
| 2026-05-13 | Push Phase 5.x back ~2 weeks | PM |
| 2026-05-13 | Convention change: numbered Epics from Phase 4.2 | PM |
| 2026-05-12 | Phase 4.1 channel strategy revised: Zalo full-parity, not Mini App | PM |
| 2026-05-12 | Phase 4.1 ship plan finalized (3 weeks) | PM |
