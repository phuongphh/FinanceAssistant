# Issue #505

[Story] P4.1-B2: Predictions vs actual calibration

**Parent Epic:** #494 (EPIC 2: Twin Polish)

Log Twin snapshot, fill actual sau 7/30/90 ngay, hien hit-rate honest framing.

- [ ] Log snapshot vao twin_calibration_snapshots khi user mo Twin
- [ ] Worker daily: fill actual_vnd, compute within_band (P10 <= actual <= P90)
- [ ] Twin view section: "Be Tien doan dung X/Y lan (Z%)" chi hien khi >=3 snapshots
- [ ] Honest framing: hit-rate <50% -> "Du phong chua chuan"
- [ ] Backfill script cho dogfood data tu Phase 4A
- [ ] Feature flag TWIN_CALIBRATION_DISPLAY_ENABLED

Close #494
