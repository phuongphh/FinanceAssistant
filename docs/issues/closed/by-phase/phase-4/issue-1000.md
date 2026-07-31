# Issue #1000

[Phase 4.7][E1 #1.3] DRIFT_WARNING_ENABLED flag + job wiring

Part of **Phase 4.7 — Guardian Layer / Epic 1**. Detail: `docs/current/phase-4.7/phase-4.7-detailed.md`.

`backend/intent/handlers/decision_flags.py`: `DRIFT_WARNING_ENABLED` (default `False`). `backend/jobs/check_empathy_triggers.py`: read the flag at the job edge and pass `include_drift` into `check_all_triggers`. Env is read only at the job edge (layer contract).

### DoD
- Test flag on/off; job passes `include_drift` correctly.
- Cooldown + quiet hours + daily cap behaviour unchanged.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01Suj5ENcPR7DooNU7GowadB
