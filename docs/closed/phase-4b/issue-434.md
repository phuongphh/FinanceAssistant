# Issue #434

[Story] P4B-S17: Low-Balance Alert Engine

**Parent Epic:** #416 (Epic 3: Cashflow Forecasting v2)

## User Story
Toi muon Be Tien canh bao truoc >=1 thang neu thang do co the thieu tien.

## Implementation Tasks
- [ ] cashflow/alert.py: check_and_send_cashflow_alerts()
- [ ] Redis dedup: cashflow_alert:{user_id}:{low_balance_month} (TTL 7d)
- [ ] Alert template in content/vi.yaml
- [ ] Default threshold = avg confirmed expense patterns
- [ ] Use get_notifiers()

## Estimate: ~1 day
## Depends on: P4B-S16

Close #416
