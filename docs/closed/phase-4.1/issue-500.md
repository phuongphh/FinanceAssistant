# Issue #500

[Story] P4.1-A5: Sentry + LLM metrics dashboard

**Parent Epic:** #493 (EPIC 1: Pre-Launch Hardening)

Wire Sentry vao FastAPI + workers. PII scrub strict.

- [ ] Sentry SDK init trong FastAPI + workers; capture voi user_id hash
- [ ] PII scrub: strip so >6 digit, email, phone; whitelist fields
- [ ] LLM metrics adapter ghi moi call vao llm_cost_log
- [ ] Metabase dashboard: error rate, p50/p95 latency, DAU
- [ ] ENV SENTRY_DSN, empty=disabled

Close #493
