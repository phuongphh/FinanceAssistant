# Issue #472

[Story] P4.1-A7: Feedback triage UI

**Parent Epic:** #463 (Epic A: Pre-Launch Hardening)

## Description
Operator co command de xem feedback pending, reply qua bot, worker alert neu SLA breach.

## Acceptance Criteria
- [ ] Migration 4.1.02: first_responded_at, sla_breach_alerted_at
- [ ] /feedback_inbox: list feedback status=open, cu nhat truoc
- [ ] /feedback_reply <id> <message>: gui reply, set first_responded_at
- [ ] /feedback_reply <id> --template <name>: template tu content/feedback/triage_responses.yaml
- [ ] feedback_sla_worker chay moi gio, alert neu open > 24h
- [ ] Permission: chi OPERATOR_TELEGRAM_ID

## Estimate: ~1.5 days
## Dependencies: None (existing /feedback tu Phase 3.8.5)

Close #463
