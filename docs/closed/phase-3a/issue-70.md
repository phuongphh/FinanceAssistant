# Issue #70

[P3A-12] Implement morning_briefing_job.py (scheduled, timezone-aware)

## Epic
Epic 2 — Morning Briefing | **Week 2** | Depends: P3A-11 | Blocks: P3A-14

## Description
Scheduled job chạy mỗi 15 phút, gửi briefing cho user nào có briefing_time trong cửa sổ 15 phút. Default 07:00 VN time.

## Acceptance Criteria
- [ ] File `app/scheduled/morning_briefing_job.py`
- [ ] Function `run_morning_briefing_job()`
- [ ] Query active users (30 days) với briefing_enabled=True
- [ ] `_is_within_15_min(now, target_time)` logic đúng (wrap midnight)
- [ ] `_already_sent_today(user_id)` tránh gửi trùng
- [ ] Send briefing với inline keyboard
- [ ] Track event `morning_briefing_sent`
- [ ] Rate limit: 1 message/second
- [ ] Error handling: 1 user fail không crash toàn job
- [ ] APScheduler trigger: `interval minutes=15`
- [ ] Timezone: Asia/Ho_Chi_Minh (UTC+7)
- [ ] Log: X briefings sent this run

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 2.3
