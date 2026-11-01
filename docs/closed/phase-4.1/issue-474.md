# Issue #474

[Story] P4.1-B2: Predictions vs actual calibration

**Parent Epic:** #464 (Epic B: Twin Polish)

## Description
Moi Twin view log snapshot, worker check sau 7d/30d/90d so voi actual net worth.

## Acceptance Criteria
- [ ] Migration 4.1.03: twin_calibration_snapshots table
- [ ] Moi Twin compute, log snapshot voi horizon 7/30/90
- [ ] Daily worker: fill actual_vnd, compute within_band (P10 <= actual <= P90)
- [ ] Twin view section: "Be Tien doan dung bao nhieu?" chi hien khi >=3 snapshots
- [ ] Honest framing: doan dung X/Y lan (Z%). Neu hit-rate <50% -> disclaimer
- [ ] Backfill script replay Twin runs tu 30 ngay truoc

## Estimate: ~2.5 days
## Dependencies: None

Close #464
