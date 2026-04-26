# Issue #71

[P3A-13] Implement daily_snapshot_job.py (23:59 auto-snapshot)

## Epic
Epic 2 — Morning Briefing | **Week 2** | Depends: P3A-2 | (Parallel với P3A-12)

## Description
Cuối ngày 23:59 tạo snapshot cho mọi active asset. Needed cho historical net worth comparison trong morning briefing.

## Acceptance Criteria
- [ ] File `app/scheduled/daily_snapshot_job.py`
- [ ] Function `create_daily_snapshots()` loop qua tất cả active assets
- [ ] Skip nếu snapshot hôm nay đã tồn tại (user đã manually update)
- [ ] source = "auto_daily"
- [ ] APScheduler: cron `23:59` daily, timezone Asia/Ho_Chi_Minh
- [ ] Batch insert cho performance (không insert 1-by-1)
- [ ] Handle unique constraint conflict gracefully (ON CONFLICT DO NOTHING)
- [ ] Log: X snapshots created, Y skipped
- [ ] Error per asset không crash loop
- [ ] Unit test với mock assets

## Estimate
~0.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 2.4
