# Issue #90

[Epic 2 / Phase 3A] Morning Briefing Infrastructure

## Phase 3A — Week 2

Epic này cover toàn bộ Morning Briefing feature: scheduled job 7h sáng adaptive theo wealth level, daily snapshot 23:59, inline keyboard, analytics tracking.

## Sub-issues
- #68 — [P3A-10] Create briefing_templates.yaml (4 wealth levels)
- #69 — [P3A-11] Build BriefingFormatter (ladder-aware, personalized)
- #70 — [P3A-12] Implement morning_briefing_job.py (scheduled, timezone-aware)
- #71 — [P3A-13] Implement daily_snapshot_job.py (23:59 auto-snapshot)
- #72 — [P3A-14] Build briefing inline keyboard (4 action buttons)
- #73 — [P3A-15] Analytics tracking for morning briefing events

## Reference
`docs/current/phase-3a-detailed.md` § 2 — Morning Briefing
`docs/current/phase-3a-issues.md` — Epic 2

## Workflow
Khi merge PR cho epic này, body chỉ cần `Closes #<this issue>` — workflow sẽ tự expand thành Closes cho tất cả sub-issues.
