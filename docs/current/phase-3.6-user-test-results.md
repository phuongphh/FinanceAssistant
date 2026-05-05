# Phase 3.6 — User Test Results

> **Story:** [P3.6-S12 / #172](../issues/active/issue-172.md)
> **Epic:** [Epic 3 / #160](../issues/active/issue-160.md)
> **Status:** Template — populate after recruiting users post-deploy.

This is the post-deploy user-test record. Phase 3.6 ships the menu
revamp behind a hard cutover — the deploy is the easy part; this
test confirms the new menu *feels* better than V1 to real users.

The protocol is lighter than Phase 3.5's 7-day study because the
change is smaller (UI revamp, not a new capability layer). 24-48h
is enough to surface the issues that matter.

---

## 1. Recruitment

| Wealth level | Count | Profile | Recruited? |
|---|---|---|---|
| **Starter** (0-30tr) | 1 | First-time user, cash-only | ☐ |
| **Mass Affluent** (200tr-1B) | 1 | Multi-asset, comfortable in app | ☐ |
| **HNW** (≥1B) | 1 | Power user, executive/entrepreneur | ☐ |

**Why this mix:** the Phase 3.6 adaptive intro is the headline UX
change. The starter ↔ HNW spread tests both ends of the tone
spectrum; Mass Affluent is the modal target user.

**Consent:** reuse Phase 3.5 consent doc. No new PII surface
introduced — the menu doesn't capture any new data.

---

## 2. Test protocol (10-15 min per user)

Each user runs the same task list. Operator records timing,
confusion points, free-form reactions.

| Task | Expected path | Timing |
|---|---|---|
| 1. Find your net worth | /menu → 💎 Tài sản → 📊 Tổng tài sản | < 30s |
| 2. See expenses by category for this month | /menu → 💸 Chi tiêu → 🏷️ Theo phân loại | < 30s |
| 3. Add a new financial goal | /menu → 🎯 Mục tiêu → ➕ Thêm mục tiêu | < 60s |
| 4. Check VNM stock price today | /menu → 📊 Thị trường → 🇻🇳 VN-Index *or* free-form "VNM giá" | < 45s |

**Capture per task:**
- Time to complete (in seconds)
- Confusion points / wrong taps
- Whether free-form was used as alternative (and why)
- Verbal reactions ("oh!", "huh?", "wait, where is...")

---

## 3. Per-user scoreboard

### User 1 — Starter

| Field | Value |
|---|---|
| Date | TBD |
| Display name | TBD |
| Net worth at test | TBD |
| Wealth level shown by menu | TBD |
| Title shown in main menu | TBD ("Trợ lý tài chính" expected) |

| Task | Time (s) | Confusion points | Used free-form? | Notes |
|---|---|---|---|---|
| 1. Net worth | | | | |
| 2. Expenses by category | | | | |
| 3. Add goal | | | | |
| 4. VNM price | | | | |

### User 2 — Mass Affluent

| Field | Value |
|---|---|
| Date | TBD |
| Display name | TBD |
| Net worth at test | TBD |
| Wealth level shown by menu | TBD |
| Title shown in main menu | TBD ("Trợ lý CFO cá nhân" expected) |

| Task | Time (s) | Confusion points | Used free-form? | Notes |
|---|---|---|---|---|
| 1. Net worth | | | | |
| 2. Expenses by category | | | | |
| 3. Add goal | | | | |
| 4. VNM price | | | | |

### User 3 — HNW

| Field | Value |
|---|---|
| Date | TBD |
| Display name | TBD |
| Net worth at test | TBD |
| Wealth level shown by menu | TBD |
| Title shown in main menu | TBD ("Personal CFO của anh/chị" expected) |

| Task | Time (s) | Confusion points | Used free-form? | Notes |
|---|---|---|---|---|
| 1. Net worth | | | | |
| 2. Expenses by category | | | | |
| 3. Add goal | | | | |
| 4. VNM price | | | | |

---

## 4. Post-test interview (15 min each)

Same five questions for every user; operator transcribes verbatim.

1. So với menu cũ, menu mới better / worse / same? Tại sao?
2. Intro của mỗi mảng có giúp bạn hiểu mảng đó làm gì không?
3. Bạn có thấy tone (cách bot nói) thân thiện không, hoặc khô khan?
4. Lúc nào bạn thấy lúng túng / không biết tap đâu?
5. Bạn sẽ recommend dùng menu hay hỏi free-form? Khi nào?

**User 1 — Starter responses:** TBD
**User 2 — Mass Affluent responses:** TBD
**User 3 — HNW responses:** TBD

---

## 5. ✅ Success criteria

The phase ships as-is when **all four** pass. If 2+ fail, file
a follow-up issue and iterate before declaring Phase 3.6 closed.

- ☐ All 3 users complete all 4 tasks.
- ☐ Average task time < 2 minutes.
- ☐ 0 users say "menu cũ tốt hơn" outright.
- ☐ ≥ 2 users notice the warmer / personalised tone unprompted.

---

## 6. Findings & decision

> Fill at completion. Mirror Phase 3A's exit-review shape: list bugs
> with severity, then decide ship / iterate / stop.

### Bugs surfaced

| Severity | Title | Repro | Owner | Status |
|---|---|---|---|---|
| | | | | |

### Decision

- ☐ **All 4 success criteria pass** → ✅ Phase 3.6 closed; archive
  legacy redirect window kicks off (1 month).
- ☐ **2-3 pass** → 🔄 Iterate one more cycle on the failing
  metric, re-test with same users.
- ☐ **< 2 pass** → 🛑 Hold archival; revisit menu copy / structure
  with the design owner.

### Owner sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Owner | | | ☐ Ship · ☐ Iterate · ☐ Hold |

---

After sign-off, this file moves with the closed Phase 3.6 issues
(handled automatically by ``.github/workflows/issue-lifecycle.yml``).
