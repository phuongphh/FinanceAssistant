# Issue #973

[Phase 4.5 / E1] 1.3 — Intent decision_shock + handler + flag

Classifier route + `backend/intent/handlers/decision_shock.py`; extract amount/timing; placeholder khi chờ; amount >50% net worth → confirm trước khi tính. Flag `SHOCK_SIMULATION_ENABLED` default `false` đọc ở worker/router.

**DoD:**
- [ ] Integration test end-to-end
- [ ] Test confirm gate
- [ ] Test flag on/off

Epic: #959 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
