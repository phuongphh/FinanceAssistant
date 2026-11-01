# Issue #679

[Story 3.1] On-Demand Twin Recompute — Phase 4.3

## Story 3.1 — On-Demand Twin Recompute

**Parent Epic:** #672 | **Estimate:** 1.5 days | **Priority:** P0 | **Surface:** Backend + Telegram

### User Story
> Là một mass affluent user vừa thêm 5tr tiết kiệm, tôi muốn thấy Twin phản ứng ngay (trong vài giây), không đợi đến briefing sáng mai.

### Requirements
- [ ] Worker listen event bus: `asset.created/updated`, `income.added`, `expense.added (>=200k)`, `goal.milestone_reached`
- [ ] Re-use Phase 4A Monte Carlo engine (KHÔNG re-implement)
- [ ] P95 latency < 5s end-to-end
- [ ] Log `twin_recompute_log` (event_id, user_id, queue_ms, compute_ms, notify_ms, total_ms, delta_pct)
- [ ] Notification only if delta crosses threshold (Story 3.5)
- [ ] Debounce: 5 actions/30s → compute once, notify once
- [ ] Idempotent: cùng user, 2 events/60s → 1 notification
- [ ] Backpressure: queue > 100 pending → skip notification, still compute background
- [ ] Retry: 3 lần exponential backoff → Sentry log
- [ ] Migration 4.3.03: `twin_recompute_log` table

### Files Touched
- `apps/workers/twin_recompute_worker.py` (new)
- `apps/twin_renderer/services/on_demand_recompute.py` (new)
- `infra/event_bus/twin_events.py` (modify)
- `db/migrations/4.3.03_twin_recompute_log.sql` (new)

### Claude Code Implementation Prompt
```
Implement Story 3.1 of Epic #672 (Phase 4.3):
On-Demand Twin Recompute

PR should close #[ISSUE_NUMBER]
```

