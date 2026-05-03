# Phase 3.5 — Pattern Improvement Process

> **Story:** [P3.5-S21 / #134](../issues/active/issue-134.md)  
> **Status:** Ongoing — weekly cadence during early launch.

The intent layer ships with ~30 hand-curated patterns. Real users will
phrase the same questions in ways nobody anticipated. This doc is the
playbook for closing those gaps continuously.

---

## When to run this loop

| Cadence | Trigger | Scope |
|---|---|---|
| **Weekly** | First 6 weeks after launch | Top 20 unclear queries |
| **Monthly** | After cadence stabilises | Aggregate + cost trend |
| **On-demand** | New feature launch (e.g., new asset type) | Domain-specific patterns |

---

## Step 1 — Find the unclear queries

The admin metrics endpoint surfaces them. You'll need the
`INTERNAL_API_KEY` from `.env` for the `X-Admin-Key` header.

```
GET /miniapp/api/intent-metrics?window_days=7
Headers: X-Admin-Key: <admin key>
```

Look at `data.top_unclear_intents` — list of `{intent, count}` rows
ordered by count desc. The `intent` field is the *attempted*
classification (e.g., `query_assets`) — high count there means the
patterns for that intent are too narrow, not that the intent is wrong.

For deeper inspection use the `events` table directly:

```sql
SELECT
  properties->>'intent' AS attempted_intent,
  COUNT(*) AS hits
FROM events
WHERE event_type = 'intent_unclear'
  AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY 1
ORDER BY hits DESC
LIMIT 20;
```

> ⚠️ **Privacy:** the analytics PII filter strips `raw_text` from
> events on write — you can NOT pull the actual user query from this
> table. To find phrasings, you have two options:
>
> 1. **Live reproduction:** ask user-test participants to share the
>    exact phrasings they tried (already covered in Story #133's
>    Day-7 interview).
> 2. **Localized debug logging:** flip
>    `backend.intent.classifier.pipeline` log level to DEBUG on a
>    single dev session to capture the raw text. Rotate logs out
>    quickly — they contain user input.
>
> Story #20 / #21 explicitly source phrasings from user testing for
> this reason.

---

## Step 2 — Decide what to do per phrasing

For each top-N phrasing, route to one of four buckets:

| Decision | Action | Confidence guidance |
|---|---|---|
| **Add new rule pattern** | Edit `content/intent_patterns.yaml` | 0.85+ if unambiguous; 0.7-0.85 if probable |
| **Improve LLM prompt** | Edit `LLM_CLASSIFIER_PROMPT` in `llm_based.py` | n/a |
| **Add to fixture file** | Edit `query_examples.yaml` | matches the rule confidence |
| **Mark as OOS** | Edit `out_of_scope_responses.yaml` + bucket detector | 0.9+ to override misfire |

**Rule of thumb:**

- Same phrasing seen ≥3 times in a week → add a rule pattern.
- Phrasing is ambiguous (could be 2+ intents) → leave it for the LLM,
  improve the prompt instead.
- Phrasing is finance-domain but oddly phrased → fixture + prompt
  improvement (the LLM should learn it).
- Phrasing is non-finance → OOS bucket.

---

## Step 3 — Add the pattern

Patterns live in `content/intent_patterns.yaml`. The classifier
lowercases AND diacritic-strips before matching, so write patterns in
accent-free form:

```yaml
query_assets:
  patterns:
    # NEW (S21): "tài sản hiện tại bao nhiêu" — informational, no possessive
    - pattern: 'tai\s*san\s+hien\s*tai.*bao\s*nhieu'
      confidence: 0.85
```

Every new pattern MUST:

1. Have a `# NEW (S21):` (or current story tag) comment with the
   sample phrasing in proper Vietnamese.
2. Use diacritic-stripped form in the regex.
3. Be added to `tests/test_intent/fixtures/query_examples.yaml` with
   the expected intent + min confidence so future regressions are
   caught.

After adding, re-run the rule layer locally to spot-check:

```python
python -c "
from backend.intent.classifier.rule_based import RuleBasedClassifier
c = RuleBasedClassifier()
print(c.classify('tài sản hiện tại bao nhiêu'))
"
```

---

## Step 4 — Verify

Three layers of verification, in order:

```
1. python -m pytest backend/tests/test_intent/test_rule_based.py
2. python -m pytest backend/tests/test_intent/test_canonical_queries.py
3. python -m pytest backend/tests/test_intent/
```

All three must pass. The canonical-query test is the contract — if a
new pattern accidentally over-matches (e.g., your new rule for
`query_assets` also catches `query_market` queries), the Group A
assertion fails fast.

After local verification, the GitHub Action `intent-tests.yml` runs
the same suites on every PR. Failure blocks merge.

---

## Step 5 — Measure improvement

After landing patterns, monitor the next 7 days of metrics:

| Signal | What to look for |
|---|---|
| `intent_classified.classifier=rule` rate | Should tick up; was 70% pre-improvement target |
| `intent_unclear` count | Should drop; specifically for the intent you patched |
| Cost per query | Should drop slightly (rule is free vs LLM cost) |

If the unclear count for your patched intent doesn't drop, the new
pattern probably has a bug — confidence too low (escalates to LLM
anyway), or regex too narrow (still misses real queries).

---

## Worked example — S21 batch (this commit)

We added 12 new patterns based on common Vietnamese phrasings:

| Phrasing | Old result | New result |
|---|---|---|
| `tài sản hiện tại bao nhiêu` | None → UNCLEAR | `query_assets` @ 0.85 |
| `em có tài sản gì` | None → UNCLEAR | `query_assets` @ 0.85 |
| `tài sản của em` | None → UNCLEAR | `query_assets` @ 0.9 |
| `tổng cộng có bao nhiêu tiền` | None → UNCLEAR | `query_net_worth` @ 0.9 |
| `tiền có bao nhiêu` | None → UNCLEAR | `query_net_worth` @ 0.7 |
| `liệt kê chi tiêu` | None → UNCLEAR | `query_expenses` @ 0.85 |
| `lương tháng bao nhiêu` | None → UNCLEAR | `query_income` @ 0.85 |
| `tổng thu nhập tháng` | None → UNCLEAR | `query_income` @ 0.9 |
| `mục tiêu hiện tại` | None → UNCLEAR | `query_goals` @ 0.85 |
| `goal hiện tại` | None → UNCLEAR | `query_goals` @ 0.85 |
| `còn bao nhiêu mới đủ mua xe` | None → UNCLEAR | `query_goal_progress` @ 0.85 |
| `liệt kê mục tiêu` | None → UNCLEAR | `query_goals` @ 0.9 |

All 12 were dry-run against canonical queries + full intent suite —
zero regressions. The patterns are tagged `# NEW (S21):` in the YAML
so a future contributor can see they came from a single batch and was
the result of this improvement-loop process.

---

## Open questions / known limits

- **Rate-of-pattern-explosion:** at >100 patterns the YAML becomes
  hard to audit. CLAUDE.md § Bẫy 2 calls this out — when we hit 100
  patterns, refactor toward a domain-specific lexer or a smarter
  classifier head. We are at ~45 after this batch.
- **Privacy vs improvement:** stripping `raw_text` from events
  protects users but slows pattern discovery. Future work could add
  a per-user opt-in "share unclear queries" flag with stricter PII
  scrubbing.
- **LLM prompt drift:** if we keep adding intents to the LLM prompt,
  it grows. Plan to extract the intent enum description into a
  reusable block so the prompt template stays one place.
