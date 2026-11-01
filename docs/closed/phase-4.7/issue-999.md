# Issue #999

[Phase 4.7][E1 #1.2] empathy trigger _check_spending_drift (include_drift param)

Part of **Phase 4.7 — Guardian Layer / Epic 1**. Detail: `docs/current/phase-4.7/phase-4.7-detailed.md`.

`backend/bot/personality/empathy_engine.py`: add `_check_spending_drift` and an `include_drift` param (default `False`) on `check_all_triggers`, mirroring `include_activation_nudge`. Priority sits between acute (`large_transaction`) and ambient (`user_silent_*`); cooldown 14 days. Calls the pure `drift_service`. The engine **never reads env** — the hourly job passes the flag decision in.

### DoD
- Unit test: trigger fires / does not fire by threshold + cooldown.
- `include_drift=False` → drift skipped, every other trigger unchanged (byte-identical pre-4.7).
- Priority-order test (drift beats silent, loses to large_transaction).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01Suj5ENcPR7DooNU7GowadB
