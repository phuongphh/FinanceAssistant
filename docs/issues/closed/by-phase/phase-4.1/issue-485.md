# Issue #485

[Story] P4.1-A5: Sentry + LLM metrics dashboard

**Parent Epic:** #478 (Epic A: Pre-Launch Hardening)

Wire Sentry vao FastAPI + workers, expose LLM metrics.

- [ ] Sentry SDK init + unhandled exception capture voi user_id tags
- [ ] PII scrub: strip regex so >6 digit, email, phone
- [ ] ENV SENTRY_DSN, empty=disabled
- [ ] LLM metrics adapter ghi moi call
- [ ] SQL examples cho operator dashboard

Close #478
