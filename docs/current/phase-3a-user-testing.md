# Phase 3A — User Testing Protocol (P3A-25)

> **Status**: Owner-driven validation experiment.
> **Goal**: Determine whether Phase 3A ships to public beta.
> **Duration**: 7 calendar days × 7 recruited users.
> **Reference**: [`docs/issues/active/issue-83.md`](../issues/active/issue-83.md)
>          · [`phase-3a-detailed.md`](phase-3a-detailed.md) § 4.2

---

## 1. Recruitment

| Wealth level | Count | Demographic guideline |
|---|---|---|
| **Starter** (0 – 30tr) | 2 | 22-25 tuổi, just started working, cash-only |
| **Young Professional** (30tr – 200tr) | 3 | 26-32 tuổi, beginning investor, có VN stocks |
| **Mass Affluent** (200tr – 1 tỷ) | 2 | 35-45 tuổi, có BĐS + stock + savings |

**Consent**: each user signs the consent form (privacy, right to delete, no recording without permission). Template in `docs/legal/user-test-consent.md` (TODO — owner to draft).

---

## 2. Daily protocol

| Day | User does | Owner does |
|---|---|---|
| **D1** | 30-min onboarding call. Add 1 cash + 1 other asset live. | Verify analytics events fire. Note questions/confusion. |
| **D2-D6** | Receive morning briefing 7h. Free use. | Daily 1-line check-in via Telegram: *"Hôm nay briefing có hữu ích không?"* |
| **D7** | 30-min interview (see § 5). | Run analytics export, fill scoreboard. |

---

## 3. Analytics tracked (already wired)

| Event | Source | Use |
|---|---|---|
| `morning_briefing_sent` | `jobs/morning_briefing_job` | Denominator for open rate |
| `morning_briefing_opened` | bot callback handler | Numerator for open rate |
| `briefing_dashboard_clicked` | bot callback handler | Funnel: briefing → dashboard |
| `briefing_story_clicked` | bot callback handler | Funnel: briefing → storytelling |
| `briefing_add_asset_clicked` | bot callback handler | Funnel: briefing → asset wizard |
| `wealth_dashboard_viewed` | `/miniapp/api/wealth/overview` | Dashboard opens (with `from` source) |
| `wealth_trend_viewed` | `/miniapp/api/wealth/trend` | Period-selector engagement |
| `miniapp_loaded` | dashboard JS beacon | Load-time p50/p95 |
| `asset_added` | wizard `complete()` | Day-1 vs day-N adds |
| `transaction_created` | storytelling handler | Storytelling completion proxy |
| `wealth_level_up` | dashboard JS (client-fired) | Confetti / level transitions |

Export with:

```bash
python -m backend.jobs.weekly_stats --since 7d --json > test_results.json
```

---

## 4. Success criteria — gate decision

All four must pass for ✅ "ship public beta":

| # | Metric | Target | How to compute |
|---|---|---|---|
| 1 | Briefing open rate | ≥ **5/7 users** opened briefing on ≥ 5 of 7 days | `briefing_opened` count grouped by user × day |
| 2 | Asset engagement | ≥ **4/7 users** added a 2nd+ asset after D1 | `asset_added` events on D2-D7 grouped by user |
| 3 | Storytelling adoption | ≥ **3/7 users** ran storytelling ≥ 3 times | `transaction_created` with `source=storytelling` |
| 4 | Willingness-to-pay | ≥ **5/7 users** said yes to ≥ 100k₫/month | Interview question Q5 (§ 5) |

---

## 5. Day-7 interview (30 min)

Audio recorded with consent. Five questions, in order, no follow-up scripting:

1. **Cảm xúc đầu tiên** — *"Lần đầu thấy net worth hiển thị, cảm giác đầu tiên của bạn là gì? Có bất ngờ gì không?"*
2. **Briefing habit** — *"Ngày nào bạn mở briefing thoải mái nhất? Ngày nào bạn skip? Tại sao?"*
3. **Storytelling tone** — *"Khi kể chuyện chi tiêu, cảm thấy natural hay forced? Có chỗ nào awkward?"*
4. **Friction** — *"Bước nào trong việc nhập tài sản khó nhất? Có lúc nào bạn muốn bỏ cuộc không?"*
5. **WTP & referral** — *"Với feature như hiện tại, bạn sẵn lòng trả bao nhiêu/tháng? Bạn sẽ giới thiệu cho ai?"*

Optional follow-up (only if time):
- *"Có một feature gì bạn ước có ngay bây giờ không?"*

---

## 6. Scoreboard template

Drop into a Google Sheet. One row per user × day; one summary row at bottom.

```
| User | Level   | D1 br_opened | D1 asset_added | D2 br_opened | ... | D7 interview |
|------|---------|--------------|----------------|--------------|-----|--------------|
| U1   | starter | 1            | 2              | 1            | ... | yes 99k WTP  |
| ...  | ...     |              |                |              |     |              |
| TOT  |         | 5/7          | 4/7            | 6/7          |     | 4/7 ≥100k    |
```

Bug list goes to a separate sheet — see `phase-3a-exit-review.md` for triage.

---

## 7. Decision matrix (out of 4 criteria)

| Criteria passed | Action |
|---|---|
| **4/4** or **3/4** | ✅ Ship Phase 3A public beta. Begin Phase 3B planning. |
| **2/4** | 🔄 1-week iteration. Re-test with 3-5 fresh users. Re-run gate. |
| **0-1/4** | 🛑 Stop. Re-evaluate product positioning before more code. |

---

## 8. Privacy / data handling

- Data stays in our PostgreSQL — no third-party analytics.
- After test, on user request, run `DELETE FROM users WHERE telegram_id = $1` cascading via FK to drop everything.
- Interview audio: stored encrypted on owner's local Mac; deleted within 30 days.
- Don't share user-level numbers in public marketing — aggregate only.
