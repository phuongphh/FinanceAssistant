# Issue #469

[Story] P4.1-A4: Daily cost report

**Parent Epic:** #463 (Epic A: Pre-Launch Hardening)

## Description
Cron 8:00 ICT gui operator bao cao cost 24h truoc.

## Acceptance Criteria
- [ ] cost_report_service.generate_daily_report(): tong cost theo provider, top 5 user, user cham 80% cap
- [ ] So tron ve 1k VND
- [ ] Neu cost > 200% avg 7 ngay -> flag dau message
- [ ] Gui qua Notifier toi OPERATOR_TELEGRAM_ID
- [ ] Tich hop vao KPI digest (A.6)

## Estimate: ~0.5 day
## Dependencies: P4.1-A3, P4.1-A6

Close #463
