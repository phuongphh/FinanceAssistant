# Issue #998

[Phase 4.7][E1 #1.1] drift_service — pure baseline + Twin-consequence delta

Part of **Phase 4.7 — Guardian Layer / Epic 1 (Drift Warnings)**. Detail: `docs/current/phase-4.7/phase-4.7-detailed.md` · `phase-4.7-issues.md`.

`backend/services/decision/drift_service.py`: pure math (no env, no commit, no transport). Baseline = median of non-transfer monthly spend over the 3 prior 30-day windows; drift = current 30-day window vs baseline. When drift exceeds threshold (>20% **and** ≥ absolute VND floor), compute the **Twin consequence** by reusing `goal_projection`: how many months the nearest goal slips if the drift pace is kept. Use `Decimal`; exclude `_INTERNAL_CATEGORIES`.

### DoD
- Service pure (no env / no commit).
- Unit test: baseline median, threshold (%+floor), goal-delay months.
- Edge cases: 0 goals → no consequence; <3 windows of history → does not fire; deficit baseline savings → no consequence.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01Suj5ENcPR7DooNU7GowadB
