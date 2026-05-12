# Issue #502

[Story] P4.1-A7: Feedback triage UI

**Parent Epic:** #493 (EPIC 1: Pre-Launch Hardening)

Operator commands de doc inbox, reply voi templates, SLA alert.

- [ ] /feedback_inbox: list status=open, cu nhat truoc; hien ID + wealth + founding flag + snippet + age
- [ ] /feedback_reply <id> <message>: gui reply, set first_responded_at, status=answered
- [ ] 5 templates trong content/feedback/triage_responses.yaml
- [ ] /feedback_reply <id> --template <name>
- [ ] feedback_sla_worker: moi gio, alert neu open >24h, 1 lan per feedback
- [ ] Permission: chi OPERATOR_TELEGRAM_ID

Close #493
