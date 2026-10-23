# Issue #248

[Story] P3.8.5-S5: ProfileStatsAggregator — auto-derived stats

**Parent Epic:** #242 (Epic 2: User Profile View)

## User Story
As a profile view, I need an aggregator that computes all auto-derived stats from existing data sources (no new data entry), so profile reflects current reality without asking user to fill forms.

## Acceptance Criteria
- [ ] File `app/profile/services/stats_aggregator.py`
- [ ] `aggregate(user_id)` → dict với all stats:
  - `account_age_days`: từ user.created_at
  - `wealth_level`: từ WealthLevelMapper
  - `wealth_progress`: progress to next level
  - `asset_types_count`: distinct asset_type (max 6)
  - `transaction_count_total`: all-time
  - `transaction_count_this_month`: current calendar month
  - `goals_active`: count goals status=active
  - `goals_completed`: count goals status=completed
  - `briefing_read_count`: từ briefing_reads table
  - `current_streak`: consecutive days với activity
  - `net_worth_change_pct`: vs first recorded (None nếu no data)
- [ ] Streak computation `_compute_streak(user_id)`:
  - "Activity" = transaction added OR briefing read OR feedback submitted
  - Reset nếu 1+ ngày không có activity
  - Brand new user → streak = 1 (today)
- [ ] **Performance:** <500ms cho power users nhiều transactions
- [ ] Efficient queries (COUNT, MAX) — không N+1
- [ ] **Không cache** (compute on-demand, fresh data)

## Test Plan
```python
async def test_aggregate_new_user():
    user = await create_brand_new_user()
    stats = await ProfileStatsAggregator().aggregate(user.id)
    assert stats["account_age_days"] == 0
    assert stats["wealth_level"]["name_vn"] == "Khởi Đầu"
    assert stats["current_streak"] == 1

async def test_streak_breaks_after_gap():
    # Activity on May 1, 2 → gap on May 3 → activity May 4
    streak = await aggregator._compute_streak(user.id)
    assert streak == 1  # Only May 4
```

## Estimate: ~1 day
## Depends on: P3.8.5-S4
