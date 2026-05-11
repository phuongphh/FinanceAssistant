# Issue #441

[Story] P4B-S24: Cashflow Alert via Zalo

**Parent Epic:** #417 (Epic 4: Zalo Adapter Foundation)

## User Story
Khi da link Zalo, toi muon nhan cashflow alert qua ca Zalo lan Telegram.

## Implementation Tasks
- [ ] get_notifiers(user_id): if zalo_user_id -> append ZaloNotifier
- [ ] format_cashflow_alert(forecast, channel='zalo') -> <= 300 chars
- [ ] Fail-open: Zalo fail -> log + continue (Telegram still sends)
- [ ] Idempotency: no duplicate in same channel

## Estimate: ~1 day
## Depends on: P4B-S17, P4B-S22, P4B-S23

Close #417
