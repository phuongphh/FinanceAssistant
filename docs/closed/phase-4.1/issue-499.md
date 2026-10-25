# Issue #499

[Story] P4.1-A4: Daily cost report

**Parent Epic:** #493 (EPIC 1: Pre-Launch Hardening)

Moi sang 8h operator nhan message tong hop cost 24h. Merge vao KPI digest (A.6).

- [ ] cost_report_service.daily_summary(date): tong cost/provider, top 5 user, user cham 80%
- [ ] Flag neu cost >200% avg 7 ngay
- [ ] Format <500 chars, rounded 1k VND
- [ ] Output consumed boi daily_kpi_digest_worker (A.6) — KHONG gui message rieng

Close #493
