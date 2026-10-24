# Issue #285

[Story] P3.9-S18: Price movement alerts (>5% in 15 min)

**Parent Epic:** #266 (Epic 4: Enhanced Briefing + Analytics + Alerts)

## User Story
As a user, I want a Telegram alert when a stock I hold moves >5% in 15 minutes.

## Acceptance Criteria
- [ ] `app/market_data/analytics/alerts.py`: check_movements(quotes)
  - Compare vs last_known 15 phút trước
  - abs(change_pct) >= 5.0 → trigger alert
- [ ] Alert format: Vietnamese, Bé Tiền persona
- [ ] Anti-spam: max 3 alerts/user/day, cooldown 30 phút/symbol
- [ ] Severity: info (5-7%), warning (7-10%), critical (>10%)
- [ ] DB log: price_alerts_log table
- [ ] User setting: notification_settings.price_alerts_enabled (default True)
- [ ] Trigger từ S7 stock updater
- [ ] Feature flag MARKET_DATA_ALERTS_ENABLED (off by default, on cuối tuần 3)
- [ ] Manual test: simulate price spike → alert sent

## Estimate: ~1 day
## Depends on: P3.9-S7
