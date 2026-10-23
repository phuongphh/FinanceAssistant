# Issue #470

[Story] P4.1-A5: Sentry + LLM metrics dashboard

**Parent Epic:** #463 (Epic A: Pre-Launch Hardening)

## Description
Wire Sentry vao FastAPI + workers, expose LLM metrics.

## Acceptance Criteria
- [ ] Sentry SDK init trong main.py + worker entrypoints
- [ ] Unhandled exception capture voi user_id + intent_name tags
- [ ] PII scrub: strip regex so >6 digit, email, phone
- [ ] ENV SENTRY_DSN, empty=disabled
- [ ] LLM metrics adapter ghi moi call vao llm_cost_log
- [ ] Operator co dashboard query-ready (SQL examples committed)
- [ ] Test exception capture trong staging

## Estimate: ~1 day
## Dependencies: P4.1-A3

Close #463
