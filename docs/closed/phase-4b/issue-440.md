# Issue #440

[Story] P4B-S23: User Zalo Linking Flow

**Parent Epic:** #417 (Epic 4: Zalo Adapter Foundation)

## User Story
Toi muon lien ket Zalo voi Be Tien de nhan thong bao cashflow.

## Implementation Tasks
- [ ] Migration: zalo_user_id + cashflow_alert_threshold columns
- [ ] zalo_link_tokens table
- [ ] /link_zalo -> 6-char token BT-XXXXXX (expires 10 min)
- [ ] Zalo webhook: POST /webhook/zalo -> match token -> link
- [ ] Confirm both channels; /unlink_zalo; /profile status

## Estimate: ~1 day
## Depends on: P4B-S21, P4B-S22

Close #417
