# Phase 3A — Exit Review (P3A-26)

> **Status**: Triggered after `phase-3a-user-testing.md` (P3A-25) completes.
> **Goal**: Triage bugs found during testing, decide ship / iterate / stop.
> **Reference**: [`docs/issues/active/issue-84.md`](../issues/active/issue-84.md)

---

## 1. Bug triage matrix

Fill during the day-7 review. Pull bugs from: user check-ins, interview notes, error logs, and `analytics.briefing_open_rate()` outliers.

| ID | Severity | Title | Repro steps | Affected level | Owner | Status |
|----|----------|-------|-------------|----------------|-------|--------|
|    |          |       |             |                |       |        |

**Severity definitions**:

| Severity | Meaning | Ship gate |
|---|---|---|
| **Critical** | Crashes app, corrupts data, blocks core flow (briefing send fails, dashboard 500) | **100% must fix** |
| **High** | Wrong number shown, broken on common device, confusing copy | **≥ 80% must fix** |
| **Medium** | Visual polish, edge-case copy, slow but works | Defer to next sprint, document |
| **Low** | Nice-to-have, future feature request | Defer or close |

---

## 2. Re-test (regression)

After fixes ship, re-run the four success criteria from `phase-3a-user-testing.md` § 4. Use the same scoreboard.

- [ ] No new Critical bugs introduced by fixes
- [ ] All Critical from § 1 reverify ✅
- [ ] ≥ 80% of High items fixed
- [ ] Briefing open rate not regressed vs. pre-fix baseline
- [ ] Dashboard p95 load time still < 2s

---

## 3. Exit decision

Tick the row that applies — the matrix mirrors `phase-3a-user-testing.md` § 7.

- [ ] **3/4 or 4/4 success criteria passed** → ✅ Ship public beta
  - Action: announce Phase 3B planning kickoff, archive active issues, freeze Phase 3A schema
- [ ] **2/4 passed** → 🔄 Iterate one more week
  - Action: pick the weakest two metrics, file follow-up issues, recruit 3-5 fresh users
- [ ] **< 2/4 passed** → 🛑 Stop and reposition
  - Action: write retrospective, share with stakeholders, hold roadmap

---

## 4. Phase 3A architectural debt to record

Living list — fill at exit, carry into Phase 3B planning.

- **Wealth dashboard cache** is in-process only. When we move past 1 user (Phase 1+) this needs to live in Redis with a per-user TTL key — see `backend/miniapp/routes.py::_wealth_cache`.
- **Snapshot trend SQL** uses `LATERAL` join over `generate_series`. Fine for ~10 assets × 365 days; revisit if a user has > 100 assets.
- **Confetti / level-up detection** is client-side only (localStorage). Server-side `wealth_level_up` event would catch users who skip the dashboard.
- **Mini App auth** caps at 24h initData freshness — long-lived sessions silently 401 on the next API call. Consider refreshing initData via `Telegram.WebApp.requestWriteAccess` if user complaints arise.

---

## 5. Sign-off

| Role | Name | Date | Decision |
|------|------|------|----------|
| Owner |  |  | ☐ Ship · ☐ Iterate · ☐ Stop |

After sign-off, move closed issues from `docs/issues/active/` to `docs/issues/closed/by-phase/phase-3a/` (auto-handled by `.github/workflows/issue-lifecycle.yml`).
