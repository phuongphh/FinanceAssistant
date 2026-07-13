# Issue #1002

[Phase 4.7][E3 #3.1] Kill switch + flag infra (DRIFT_WARNING / SCAM_CHECK)

Part of **Phase 4.7 — Guardian Layer / Epic 3 (Guardrails & Kill Switch)**. Detail: `docs/current/phase-4.7/phase-4.7-detailed.md`. `red-line`.

`backend/intent/handlers/decision_flags.py`: add `SCAM_CHECK_ENABLED` (default `False`) read at the handler edge — off ⇒ scam_check delegates to `AdvisoryHandler` (byte-identical pre-4.7), never `out_of_scope`. Kill-switch mechanism (owner decision #3): env flag read every request at the edge, but env only changes on process restart ⇒ to disable in <24h **without** a code deploy, v1 uses the **restart runbook** (set env + `scripts/rebuild-finance-prod.sh` / launchd reload). Escalate to a DB/config runtime toggle only if §8 one-strike demands instant-off. §8 runbook: one harmful wrong-verdict report ⇒ kill within 24h + post-mortem before re-enable.

> Scope note: this PR lands the **flag infra only** (both flags, default off). The scam-check handler/service/copy land with E2, which is gated on legal sign-off.

### DoD
- Both flags default off; helpers mirror the existing `_enabled(env, *, default)` pattern.
- Restart-based kill-switch runbook documented (no code deploy needed to flip).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01Suj5ENcPR7DooNU7GowadB
