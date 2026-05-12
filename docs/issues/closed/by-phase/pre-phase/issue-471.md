# Issue #471

[Story] P4.1-A6: Daily KPI digest cron

**Parent Epic:** #463 (Epic A: Pre-Launch Hardening)

## Description
Cron 8:00 ICT moi sang gui operator KPI tong hop.

## Acceptance Criteria
- [ ] daily_kpi_digest_worker chay 8:00 ICT
- [ ] Gui 1 message Telegram toi OPERATOR_TELEGRAM_ID:
  - DAU/WAU/MAU, so Twin view 24h, intent accuracy, churn signals, top 3 feedback pending, cost report
- [ ] Length < 2000 chars, Markdown
- [ ] Cron fail -> Sentry alert
- [ ] Script scripts/kpi_digest.py runnable standalone voi --date

## Estimate: ~1 day
## Dependencies: P4.1-A3, P4.1-A7

Close #463
