# Issue #501

[Story] P4.1-A6: Daily KPI digest cron

**Parent Epic:** #493 (EPIC 1: Pre-Launch Hardening)

Cron 8h sang gui 1 message Telegram den operator gom cost + KPI + feedback queue.

- [ ] Cron 8:00 ICT -> OPERATOR_TELEGRAM_ID
- [ ] Sections: Cost/A.4, Engagement (DAU/WAU, Twin views, onboarding completed), Quality (intent accuracy, emoji breakdown), Churn signals, Feedback queue
- [ ] Format <4000 chars
- [ ] Cron fail -> Sentry alert
- [ ] Script scripts/kpi_digest.py standalone voi --date

Close #493
