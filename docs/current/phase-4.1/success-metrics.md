# Phase 4.1 — Success Metrics Rubric

> **Story:** P4.1-C2 (Issue #507)
> **Owner:** Operator (= founder) reading the daily KPI digest.
> **Audience:** Operator + on-call dev during the 50-user soft launch.
> **Cadence:** All metrics computed daily via the `daily_kpi_digest` cron;
> the qualitative metric (Twin satisfaction) is a manual 10-user interview
> at the D7 mark.

This rubric is the **scoreboard for soft launch**. We did not ship a
feature; we shipped a hypothesis. These metrics tell us whether the
hypothesis survived contact with 50 real users.

If you change one of these targets, you owe the team a 3-line rationale
in the PR description — moving the goalposts after the fact is the most
common way soft launches fool themselves.

---

## 0. Cohort definition

Every query below assumes:
- **`founding_cohort`** = `users WHERE is_founding_member = TRUE`.
- **`active(day)`** = user sent ≥ 1 message OR opened the Mini App in
  the given day (uses `intent_logs` + `briefing_logs.opened_at`).
- All timestamps in **Asia/Ho_Chi_Minh** unless noted.

Set them up once as a CTE in the daily digest job to avoid drift between
metric SQLs.

---

## 1. D1 retention ≥ 70%

**Definition:** Of founding members who completed onboarding yesterday,
the % who were active today.

**Why this target?** D1 is the loosest survival signal — anything
under 70% on a hand-picked cohort means the first session left them
confused, not curious.

**SQL:**
```sql
WITH onboarded_y AS (
  SELECT u.id
  FROM users u
  JOIN onboarding_sessions s ON s.user_id = u.id
  WHERE u.is_founding_member = TRUE
    AND s.completed_at::date = CURRENT_DATE - INTERVAL '1 day'
),
active_today AS (
  SELECT DISTINCT user_id
  FROM intent_logs
  WHERE created_at::date = CURRENT_DATE
)
SELECT
  COUNT(*) FILTER (WHERE a.user_id IS NOT NULL)::float
    / NULLIF(COUNT(*), 0) AS d1_retention,
  COUNT(*) AS cohort_size
FROM onboarded_y o
LEFT JOIN active_today a ON a.user_id = o.id;
```

**Cron:** Daily 08:00 ICT (inside `daily_kpi_digest_job`).
**Surface:** "Engagement section" of the digest.

---

## 2. D7 retention ≥ 40%

**Definition:** Of founding members onboarded 7 days ago, the % active
in the 7-day window starting from D2 (i.e. days 2..8 inclusive).

**Why this target?** D7 is the leading indicator we care most about —
40% on a small cohort is the threshold that justified the V2 pivot from
SMS-forwarding. Below 40% means the daily briefing didn't earn the slot.

**SQL:**
```sql
WITH onboarded_d7 AS (
  SELECT u.id
  FROM users u
  JOIN onboarding_sessions s ON s.user_id = u.id
  WHERE u.is_founding_member = TRUE
    AND s.completed_at::date = CURRENT_DATE - INTERVAL '7 days'
),
active_d2_d8 AS (
  SELECT DISTINCT user_id
  FROM intent_logs
  WHERE created_at::date
    BETWEEN CURRENT_DATE - INTERVAL '6 days' AND CURRENT_DATE
)
SELECT
  COUNT(*) FILTER (WHERE a.user_id IS NOT NULL)::float
    / NULLIF(COUNT(*), 0) AS d7_retention,
  COUNT(*) AS cohort_size
FROM onboarded_d7 o
LEFT JOIN active_d2_d8 a ON a.user_id = o.id;
```

**Cron:** Daily 08:00 ICT.
**Surface:** Engagement section.

---

## 3. % user mở Twin trong session đầu ≥ 70%

**Definition:** Of founding members who completed onboarding, the % whose
`onboarding_sessions.first_twin_shown_at` is **non-null** (i.e. the Twin
chart was actually rendered, not just compute-attempted).

**Why this target?** This is the wow-moment proxy. If a user finishes
onboarding without seeing the Twin, A.2 (first-Twin shortcut) is broken
— either the compute is failing or the chart render is.

**SQL:**
```sql
SELECT
  COUNT(*) FILTER (WHERE first_twin_shown_at IS NOT NULL)::float
    / NULLIF(COUNT(*), 0) AS twin_shown_pct,
  COUNT(*) AS cohort
FROM onboarding_sessions s
JOIN users u ON u.id = s.user_id
WHERE u.is_founding_member = TRUE
  AND s.completed_at IS NOT NULL;
```

**Cron:** Daily 08:00 ICT.
**Surface:** Engagement section.

---

## 4. % user log ≥ 1 asset thật trong 7 ngày đầu ≥ 60%

**Definition:** Of founding members onboarded ≥ 7 days ago, the % who
have at least one **non-demo** row in `assets` created within the first
7 days. Demo placeholders are excluded by checking
`onboarding_sessions.demo_mode_used` — if the only asset they ever
created came from the demo flow, they don't count.

**Why this target?** Twin is only useful with real numbers. Sub-60%
means users abandoned somewhere between "saw the demo" and "trusted us
with a real figure" — a copy/UX problem, not a tech one.

**SQL:**
```sql
WITH founding_d7 AS (
  SELECT u.id, u.created_at
  FROM users u
  WHERE u.is_founding_member = TRUE
    AND u.created_at <= NOW() - INTERVAL '7 days'
),
real_assets AS (
  SELECT DISTINCT a.user_id
  FROM assets a
  JOIN founding_d7 f ON f.id = a.user_id
  WHERE a.created_at <= f.created_at + INTERVAL '7 days'
    AND a.deleted_at IS NULL
    AND COALESCE(a.is_placeholder, FALSE) = FALSE
)
SELECT
  COUNT(*) FILTER (WHERE r.user_id IS NOT NULL)::float
    / NULLIF(COUNT(*), 0) AS real_asset_pct,
  COUNT(*) AS cohort
FROM founding_d7 f
LEFT JOIN real_assets r ON r.user_id = f.id;
```

> **Note:** `assets.is_placeholder` was introduced in Phase 4A. If
> rolling back to a pre-4A snapshot, replace with
> `current_value_vnd != 50_000_000` heuristic.

**Cron:** Daily 08:00 ICT (after the briefing window so today's onboards
aren't double-counted).
**Surface:** Engagement section.

---

## 5. Intent classification accuracy ≥ 85%

**Definition:** Of `intent_logs` rows in the last 24h, the % with
`outcome = 'confirmed'` (user confirmed the parse) vs `'clarified'`
(bot asked for more info) vs `'misexecuted'` (user replied with
correction or `/cancel`).

**Why this target?** 85% is the threshold below which clarification
fatigue eats retention — every 6th message asking "Bạn có ý là …?" is
the line where confidence drops below the wow.

**SQL:**
```sql
SELECT
  outcome,
  COUNT(*) AS n,
  COUNT(*)::float / SUM(COUNT(*)) OVER () AS pct
FROM intent_logs
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY outcome
ORDER BY n DESC;
```

> **Implementation note:** `intent_logs.outcome` is the column populated
> by the worker after the user's next reply (or after a 5-min idle
> timer). If a row never gets an outcome it stays `'unknown'` and is
> excluded from the denominator.

**Cron:** Daily 08:00 ICT.
**Surface:** Quality section.

---

## 6. Feedback SLA (response < 24h) ≥ 95%

**Definition:** Of feedbacks created in the last 7 days where
`status` is no longer `new`, the % with
`first_responded_at - created_at < 24 hours`.

**Why this target?** This is the operator's personal commitment, not an
LLM metric. 95% says: 1 in 20 was late — acceptable, the rest hit the
SLA. Anything below means the operator is the bottleneck.

**SQL:**
```sql
SELECT
  COUNT(*) FILTER (
    WHERE first_responded_at IS NOT NULL
      AND first_responded_at - created_at < INTERVAL '24 hours'
  )::float / NULLIF(COUNT(*), 0) AS sla_hit_pct,
  COUNT(*) AS total
FROM feedbacks
WHERE created_at >= NOW() - INTERVAL '7 days'
  AND status != 'new';
```

**Cron:** Daily 08:00 ICT (plus hourly `feedback_sla_worker` for
real-time breach alerts — see Story A.7).
**Surface:** "Feedback queue" section.

---

## 7. In-onboarding emoji signal — 😍 ≥ 50%

**Definition:** Of `feedbacks` rows with
`onboarding_emoji_signal IS NOT NULL` from the last 7 days, the % with
signal `love`. Distribution across 😍 / 🤔 / 😕 reported on the digest.

**Why this target?** The post-Twin emoji tap is our highest-trust
qualitative signal (Story A.2). It's the only metric collected at peak
dopamine, before survivorship bias kicks in. 😍 ≥ 50% means the wow is
landing for at least half the cohort. 😕 > 30% triggers a kill-criteria
review (see kill-criteria.md §5).

**SQL:**
```sql
SELECT
  onboarding_emoji_signal,
  COUNT(*) AS n,
  COUNT(*)::float / SUM(COUNT(*)) OVER () AS pct
FROM feedbacks
WHERE created_at >= NOW() - INTERVAL '7 days'
  AND onboarding_emoji_signal IS NOT NULL
GROUP BY onboarding_emoji_signal
ORDER BY n DESC;
```

**Cron:** Daily 08:00 ICT.
**Surface:** Quality section.

---

## 8. Twin satisfaction sau D7 — qualitative

**Definition:** Manual semi-structured interview with **10 founding
members chosen at random** at the D7 mark. 15 minutes each, 3 questions:

1. "Khi Bé Tiền vẽ Twin lần đầu, bạn nghĩ gì?"
2. "Bạn có chia sẻ Bé Tiền với ai chưa? Tại sao có / không?"
3. "Nếu Bé Tiền dừng hoạt động ngày mai, bạn có tiếc không?"

**Why this target?** Quantitative metrics can hide net-negative UX
behind retention inertia (Vietnamese users are polite — they keep the
bot open even when annoyed). 10 conversations at D7 catches signals
the digest cannot.

**Sampling SQL** (operator runs at start of week 2):
```sql
SELECT u.id, u.display_name, u.founding_member_sequence
FROM users u
JOIN onboarding_sessions s ON s.user_id = u.id
WHERE u.is_founding_member = TRUE
  AND s.completed_at::date BETWEEN CURRENT_DATE - INTERVAL '8 days'
                              AND CURRENT_DATE - INTERVAL '6 days'
ORDER BY random()
LIMIT 10;
```

**Cron:** N/A — manual workflow. Output goes into
`docs/current/phase-4.1/d7-interviews.md` (created when the first batch
finishes; not pre-staged here).

---

## Acceptance — what "green" looks like

For Phase 4.1 to be declared a success on metrics alone, **5 of the 7
quantitative metrics must hit target** AND the qualitative interview
must surface ≥ 3 "yes" answers to Q3 (would miss the product). Missing
any one quantitative target by < 10% is "yellow" — investigate, don't
panic. Missing by > 10% on 3+ metrics is "red" → see
[kill-criteria.md](kill-criteria.md).

---

## Where to read these in the digest

The 08:00 KPI digest message is structured to put metrics in this
order — operator can read top-down and stop at the first red flag:

```
🚨 (alert flags if any)
💰 Cost section  → §A.4 daily cost report
👥 Engagement    → §1 D1, §2 D7, §3 Twin shown, §4 Real assets
✅ Quality       → §5 Intent accuracy, §7 Emoji signal
⏰ Feedback      → §6 SLA + top-3 unanswered

```

If the digest job fails, Sentry pages the operator. Silent miss = bug.

---

*Last updated: Phase 4.1 implementation — 12/05/2026.*
