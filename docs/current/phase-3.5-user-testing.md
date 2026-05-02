# Phase 3.5 — User Testing Protocol (P3.5-S20)

> **Story:** [#133](../issues/active/issue-133.md)  
> **Status:** ⚠️ Gate issue — quyết định ship to public beta hay iterate  
> **Duration:** 7 calendar days × 5 recruited users  
> **Reference:** [`phase-3.5-detailed.md`](phase-3.5-detailed.md) § Tuần 3

This protocol structures the human-in-the-loop validation that the
intent layer (Epics 1-3) actually delivers a "feel intelligent" UX.
Automated tests prove patterns hit; only real users prove Bé Tiền
*feels* like it understands them.

---

## 1. Recruitment

| Wealth level | Count | Profile |
|---|---|---|
| **Starter** (0-30tr)        | 2 | 22-25, vừa đi làm, cash-only |
| **Mass Affluent** (200tr-1B) | 2 | 35-45, có BĐS + stock + savings |
| **HNW** (≥1B)               | 1 | Executive / entrepreneur, multi-asset |

**Why this mix:** the response-style tests (Story #126) fall apart if
all five users are the same level. Cover Starter + HNW so opposite
ends get walk-through coverage; Mass Affluent x2 because that band is
the meat of the V2 target market.

**Consent:** each user signs `docs/legal/user-test-consent.md` (TODO —
owner to draft if it doesn't exist yet). Privacy commitments:

- Raw transcripts (`raw_text`) are stripped from analytics by the PII
  filter — verify at `backend/analytics.py::sanitize_properties`.
- Right to delete: `DELETE /api/v1/users/{id}` cascades to events.
- No screen-recording without explicit per-call consent.

---

## 2. Daily protocol

| Day | User does | Owner does |
|---|---|---|
| **D1** | 30-min onboarding call. Add 1 cash + 1 other asset live. Walk through 5 free-form queries — owner observes. | Note rough/confusing prompts. Check `intent_classified` events fire. |
| **D2-D6** | Organic use. Receive briefing 7AM. Try at least 5 queries / day. | 1-line daily check-in: *"Hôm nay Bé Tiền hiểu bạn được mấy lần?"* |
| **D7** | 30-min interview (§ 4). | Run scoreboard export, file lessons. |

The "5 queries / day" floor is a gentle ask — don't push if a user
runs dry. The point is real-world usage, not synthetic load.

---

## 3. Analytics tracked

Phase 3.5 adds these to the existing Phase 3A funnel events. All fire
via `backend/bot/handlers/free_form_text.py` and `voice_query.py`.

| Event | Triggered when | Use |
|---|---|---|
| `intent_classified` | every classified query | Volume + classifier split + latency |
| `intent_handler_executed` | confident execution | Success rate |
| `intent_unclear` | confidence < 0.5 OR UNCLEAR | Misses to mine |
| `intent_clarification_sent` | Epic 2 clarify flow | Disambiguation rate |
| `intent_clarification_resolved` | user picked an option | Resolution rate |
| `intent_confirm_sent` | Epic 2 write-confirm | Confirm flow volume |
| `intent_confirm_accepted` / `intent_confirm_rejected` | callback | Accuracy of medium-confidence guesses |
| `intent_oos_declined` | OOS handler fired | Buckets to expand |
| `intent_followup_tapped` | Epic 3 follow-up button | Engagement w/ suggestions |
| `llm_classifier_call` | LLM classifier ran (cache miss) | Cost denominator |
| `advisory_response_sent` | advisory handler succeeded | Advisory volume |
| `advisory_rate_limited` | 6th call in 24h | Quota hit rate |
| `voice_query_received` | voice query transcribed | Voice usage |
| `voice_query_failed` | Whisper / download error | Reliability |

Export the raw events for a user:

```sql
SELECT timestamp, event_type, properties
FROM events
WHERE user_id = :user_id
  AND timestamp >= NOW() - INTERVAL '7 days'
  AND event_type LIKE 'intent_%'
   OR event_type LIKE 'voice_query_%'
   OR event_type LIKE 'advisory_%'
ORDER BY timestamp;
```

Or via the admin metrics endpoint:

```
GET /miniapp/api/intent-metrics?window_days=7
Headers: X-Admin-Key: $INTERNAL_API_KEY
```

---

## 4. Scoreboard (per-user)

Filled in on Day 7 from the analytics export. Template:

| Metric | Target | User 1 | User 2 | User 3 | User 4 | User 5 |
|---|---|---|---|---|---|---|
| Briefings opened (of 7 sent) | ≥4 | | | | | |
| Total queries (D2-D6) | ≥25 | | | | | |
| `intent_classified.classifier=rule` rate | ≥60% | | | | | |
| `intent_unclear` rate | ≤20% | | | | | |
| `intent_handler_executed` rate | ≥70% | | | | | |
| Avg response latency (ms) | ≤2000 | | | | | |
| `advisory_response_sent` count | informational | | | | | |
| `voice_query_received` count | informational | | | | | |
| Day-7 rating (1-10) | ≥7 | | | | | |
| Day-7 free-form: "Bé Tiền hiểu mình tốt hơn rồi"? | informational | | | | | |

Use `backend/scripts/intent_user_scorecard.py` (added in this commit)
to generate the per-user row from analytics events; copy/paste into
this table.

---

## 5. Day-7 interview script (30 min)

Script the questions; answers are free-form. Don't lead.

1. **(2 min)** Trên thang 1-10, Bé Tiền hiểu được những gì bạn hỏi
   trong tuần qua bao nhiêu? *(record number)*
2. **(5 min)** Show me the top 3 queries that DIDN'T work as you
   expected. What did you mean? What did Bé Tiền do? *(write each
   down — feeds Story #134)*
3. **(5 min)** Khi Bé Tiền không hiểu (clarification button), bạn
   tap không? Nếu không, tại sao? *(checks Epic 2 UX)*
4. **(5 min)** Có bao giờ Bé Tiền execute sai action mà bạn không
   muốn không? *(red-line check — block ship if any user says yes)*
5. **(5 min)** Briefing 7h sáng có hữu ích không? Bạn có open ngay
   khi nhận không? *(continuity check with Phase 3A)*
6. **(3 min)** Câu hỏi nào bạn muốn hỏi nhưng Bé Tiền chưa support?
   *(Phase 4 backlog)*
7. **(5 min)** Free-form — gì nữa muốn nói? *(silent → wait)*

Record audio with consent; transcribe verbatim into
`docs/research/phase-3.5-interview-<user>.md` (gitignored unless
anonymized).

---

## 6. ✅ Success Criteria — ship to public beta IF ALL pass

These are gates, not goals. Failing one means iterate before ship,
not "shipping anyway with a known issue."

- [ ] **≥4/5** users rate experience **≥7/10**.
- [ ] **0** users report Bé Tiền executed a wrong write action.
- [ ] **3/5** users say verbatim or near-verbatim *"Bé Tiền hiểu mình
      tốt hơn rồi"* / *"smarter"* / *"intuitive"*.
- [ ] Per-user `intent_unclear` rate **≤25%** (averaged across users).
- [ ] No user's confirm-rejection rate **>30%** (a high reject rate
      means the medium-confidence flow is guessing wrong too often).

If all five pass → ship to public beta and proceed to Story #134
(pattern improvement) on real production data.

If any fail → file findings, iterate, re-run with same five users
after fix.

---

## 7. Deliverables

Produced at end of Day 7:

- [ ] **Scoreboard spreadsheet** (this doc, filled in).
- [ ] **Top 5 query patterns NOT in current rules** — input for
      Story #134.
- [ ] **Top 3 confusing responses** — input for personality /
      content YAML refinement.
- [ ] **Decision document**: ship to public beta OR iterate, with
      rationale tied to the gates above. Filed at
      `docs/current/phase-3.5-ship-decision.md`.
