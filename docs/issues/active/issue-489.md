# Issue #489

[Story] P4.1-B2: Predictions vs actual calibration

**Parent Epic:** #479 (Epic B: Twin Polish)

Moi Twin view log snapshot, worker check sau 7d/30d/90d so voi actual net worth.

- [ ] Migration: twin_calibration_snapshots table
- [ ] Daily worker: fill actual_vnd, compute within_band (P10 <= actual <= P90)
- [ ] Twin view section hien hit-rate khi >=3 snapshots
- [ ] Honest framing: hit-rate <50% -> disclaimer
- [ ] Backfill script replay Twin runs tu 30 ngay truoc

Close #479
