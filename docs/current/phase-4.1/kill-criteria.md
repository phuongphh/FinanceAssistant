# Phase 4.1 — Kill Criteria

> **Story:** P4.1-C3 (Issue #508)
> **Owner per criterion:** see column below. Final go/no-go: operator (=
> founder).
> **Cadence:** Reviewed weekly during the soft-launch retro. Any single
> trigger fires → 24h escalation, not a slow drift.

Kill criteria exist so we **commit in advance** to act on signals when
we see them. Without them, sunk-cost reasoning ("we shipped this, let's
fix it once more") quietly extends the runway of bad bets. The cost of
mis-firing a criterion is a one-week debate. The cost of ignoring a
real signal is a quarter of a year.

**Rule of three for every criterion:**
1. **Owner** — who watches it.
2. **Threshold** — what number triggers action.
3. **Action plan** — what we do in the next 48h if it trips.

If a criterion is missing one of the three, it's a wish, not a kill
criterion. Reject the PR.

## Table of contents

1. [4-week retention < 20%](#1--4-week-retention--20)
2. [Cost per active user > 50.000đ/tháng](#2--cost-per-active-user--50000đtháng)
3. [Critical bug rate (Sentry P1) > 1/ngày](#3--critical-bug-rate-sentry-p1--1ngày)
4. [Bé Tiền persona violation reported > 5/tuần](#4--bé-tiền-persona-violation-reported--5tuần)
5. [In-onboarding emoji signal 😕 > 30%](#5--in-onboarding-emoji-signal---30)
6. [Twin within-band hit rate < 40% sau 90 ngày](#6--twin-within-band-hit-rate--40-sau-90-ngày)
7. [Positioning misalignment > 30%](#7--positioning-misalignment--30)

---

## §1 — 4-week retention < 20%

**Owner:** Operator
**Source:** D28 cohort retention from `intent_logs` vs `users` joined
on `is_founding_member`.

**Threshold:** Of founding members onboarded ≥ 28 days ago, < 20% sent
any message in the last 7 days.

**Why this is the kill line:** D7 ≥ 40% is the target, D28 ≥ 20% is
roughly the "halved each week" decay we can tolerate for a soft launch.
Below 20% means even the personal-network cohort dropped — there is
no PMF in this positioning.

**Action plan if tripped:**
1. **Day 0:** Stop new invite distribution. Investigate WHY the cohort
   stopped — qualitative interview with 5 churned users.
2. **Day 1–3:** If reason is "Twin didn't earn its slot" → pivot
   positioning to expense-tracking-first (defer Twin to Phase 5+).
   If reason is "morning briefing felt like spam" → adjust briefing
   cadence (3×/week not daily).
3. **Day 7:** Go/no-go on a redesigned A.1 onboarding. If a redesign
   isn't believable, **kill the product** and write the post-mortem.

---

## §2 — Cost per active user > 50.000đ/tháng

**Owner:** Operator
**Source:** `llm_cost_log` summed over the past 30d, divided by MAU
(active users in that window).

**Threshold:** Average ≥ 50.000đ/month/active user, sustained over
≥ 2 weeks.

**Why this is the kill line:** Pro Tier is 88.000đ — unit economics
require cost ≤ 30% of price (industry norm for AI products is 20–40%).
At 50k/user cost, gross margin on Pro is < 45% before fixed costs.
We can't grow into that.

**Action plan if tripped:**
1. **Day 0:** Operator pulls top-10 spenders from
   `llm_cost_log` and audits their flows. Look for `ocr_receipt` loops
   or `transcribe` retries.
2. **Day 1–3:** Apply two cuts in parallel:
   - Lower the free-tier budget cap from 30k → 20k (squeeze the long
     tail). Warn users at 50%.
   - Switch the storytelling prompt to DeepSeek-Coder-v3 instead of
     v3.5 if available — same accuracy at half the cost (need to
     re-run `tests/prompts/`).
3. **Day 7:** If still > 50k/user, freeze new features and run a
   prompt-tuning sprint. If still > 50k after sprint, **defer Pro
   launch** (Phase 5.7) until margin is fixed.

---

## §3 — Critical bug rate (Sentry P1) > 1/ngày

**Owner:** On-call dev
**Source:** Sentry — events at `level=fatal` OR
`fingerprint matches known-broken`, per 24h window.

**Threshold:** > 1 P1 event/day averaged over the 50-user cohort for
≥ 3 consecutive days.

**Why this is the kill line:** At 50 users a single recurring crash
poisons trust. Bug rate isn't about "bugs exist" (they always do); it's
about "bugs reach users faster than fixes do." 3 days at >1/day means
the fix cadence is the bottleneck.

**Action plan if tripped:**
1. **Day 0:** Freeze all feature merges to main. Only fix PRs land.
2. **Day 1–3:** Daily 30-min on-call triage. Affected user gets a
   manual `/feedback_reply` apology with ETA — don't wait for the
   24h SLA worker.
3. **Day 4:** If queue not empty, escalate: dev pauses Phase 4.1
   stretch goals, focuses 100% on stabilization. **Defer launch
   announcement** until 5 days no P1.

---

## §4 — Bé Tiền persona violation reported > 5/tuần

**Owner:** Operator
**Source:** Manual tagging in `/feedback_inbox` — any feedback flagged
`category=persona_violation` by operator.

**Threshold:** ≥ 5 distinct user reports per week, OR ≥ 3 reports about
the SAME copy line.

**Why this is the kill line:** Bé Tiền's persona is the differentiator
— warm, supportive, never judgey. If the persona breaks (even on
non-money topics — e.g., implying user is poor for asking what 1tr is),
every other metric stops mattering. This is the brand-risk red line.

**Action plan if tripped:**
1. **Day 0:** Operator quotes the offending output(s) verbatim into
   `tests/prompts/persona_regressions.txt` (NEW file). Spawns
   `prompt-tester` agent to re-validate the affected prompt against
   the regression set.
2. **Day 1–3:** Rewrite the failing prompt or content YAML. **Block
   merge** until the regression test passes.
3. **Day 7:** If persona violations recur from a different surface
   (different prompt, different YAML), **audit all prompts** — the
   problem is systemic, not local.

---

## §5 — In-onboarding emoji signal 😕 > 30%

**Owner:** Operator
**Source:** `feedbacks.onboarding_emoji_signal = 'dislike'` over the
total of `(love + confused + dislike)` for the 50 founding members.

**Threshold:** > 30% of in-onboarding emoji taps are 😕 within the
first 25 founding members onboarded.

**Why this is the kill line:** The post-Twin emoji is collected at the
ONE moment of peak honesty — right after the wow-moment is supposed to
land. If 1 in 3 users is unimpressed at peak, the wow does not exist.
A.1 + A.2 are first-impression broken, and we'd be scaling to 50 users
who all hit the same broken first impression.

**Action plan if tripped:**
1. **Day 0:** Stop further invite distribution. Email/DM the 😕 voters
   personally: "Bạn có 5 phút giúp Bé Tiền hiểu vì sao không?"
2. **Day 1–3:** Watch a screen-recording of 3 users redoing onboarding
   (manual session capture; Vietnam UTC permits this). Identify the
   exact bounce moment.
3. **Day 7:** Re-ship A.1 + A.2 — different goal copy, different
   narrative ordering, possibly skip the cone chart on first run and
   show a single number ("Đến 65 tuổi bạn sẽ có X tỷ"). Re-run the
   first-session test with 5 fresh accounts. **No more invites until
   😕 < 20% on a fresh cohort of 10.**

---

## §6 — Twin within-band hit rate < 40% sau 90 ngày

**Owner:** On-call dev (twin engine)
**Source:** `twin_calibration_snapshots` — % rows where
`within_band = TRUE`, restricted to snapshots whose
`predicted_at` ≥ 90 days ago (so all 3 horizons have resolved).

**Threshold:** < 40% within-band hit rate after the first batch of
90-day snapshots have actuals filled in (~ Phase 5.0 timeframe, but
this criterion is staged now).

**Why this is the kill line:** Honest framing only works when the
model is roughly right. If the cone misses on > 60% of predictions,
"Bé Tiền đoán đúng X lần" becomes embarrassing instead of building
trust. The calibration storytelling (B.2) is dependent on this.

**Action plan if tripped:**
1. **Day 0:** Hide the "🎯 Bé Tiền đoán đúng bao nhiêu?" section behind
   a feature flag. Keep logging snapshots, stop displaying the score.
2. **Day 1–7:** Re-run twin model calibration on the live data —
   widen the cone (lower P10 floor, raise P90 ceiling) so the band
   covers more honest variance. Or, switch to a 50/30/20 weighting of
   historical volatility vs forward returns.
3. **Day 14:** Backfill calibration with the new model. If hit-rate
   still < 50%, **defer the calibration-storytelling section
   entirely** — the engine is not ready to make claims, even honest ones.

---

## §7 — Positioning misalignment > 30%

**Owner:** Founder/PM
**Source:** `positioning_survey_responses` from the Phase 4.2 Day 7
micro-survey. Misalignment = % users choosing option 1
("App quản lý chi tiêu") or option 4 ("Chưa hiểu rõ").

**Threshold:** > 30% misalignment, starting from week 2 after Phase 4.2
launch, and only once the survey has ≥ 20 responses.

**Why this is the kill line:** Bé Tiền is intended to be a Personal CFO
/ future-looking financial companion, not only an expense tracker. If
more than 30% of early users either see an expense app or do not
understand the product, acquisition would amplify the wrong mental
model instead of validating the proposition.

**Action plan if tripped:**
1. **Day 0:** Freeze acquisition and stop expanding the founding cohort.
   Read all survey + qualitative feedback from the affected users.
2. **Day 1–14:** Redesign the welcome copy, first Twin narrative, and
   briefing intro as one positioning system. Do not patch only one line.
3. **Day 14:** Re-run with a fresh cohort of 20 users. Resume
   acquisition only if option 2/3 reaches ≥ 60% and misalignment drops
   below 30%.

---

## Operating procedure

- The daily KPI digest (08:00 ICT) is the primary signal feed. Operator
  reads it every morning, full stop — non-negotiable for the soft
  launch period.
- When a kill criterion trips, the operator drops a **Day 0 message
  into the team thread** within 4 hours, with one of three labels:
  - 🟡 **Watch**: signal noisy, decide in 48h.
  - 🟠 **Mitigate**: criterion tripped, action plan starts now.
  - 🔴 **Kill / Pivot**: criterion tripped + mitigation already
    attempted → invoke action plan day-7 step.
- The Day-7 action of every criterion is a **commit point**: if we get
  there and the metric hasn't moved, we follow the kill/pivot
  language, no "one more week" loops.

This rubric is not a contract with users — those promises live in
[founding-promise.md](../founding-promise.md). This is a contract with
ourselves.

---

*Last updated: Phase 4.2 Epic 3 positioning validation — 13/05/2026.*
