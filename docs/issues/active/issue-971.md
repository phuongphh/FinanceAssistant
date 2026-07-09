# Issue #971

[Phase 4.5 / E1] 1.1 — shock_simulation_service.simulate_shock()

`backend/services/decision/shock_simulation_service.py` — copy portfolio in-memory, inject `LifeEventInjection` giả định vào `simulate_portfolio()` paths, trả delta P10/P50/P90. KHÔNG persist.

**DoD:**
- [ ] Unit test delta hợp lý với shock các cỡ
- [ ] Test DB không có row mới sau khi chạy
- [ ] Test shock > net worth → floor 0 không crash

Epic: #959 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
