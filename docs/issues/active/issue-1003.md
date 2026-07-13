# Issue #1003

[Phase 4.7][E3 #3.2] QUERY_TYPE_SCAM_CHECK constant (drift stays off decision_query_log)

Part of **Phase 4.7 — Guardian Layer / Epic 3**. Detail: `docs/current/phase-4.7/phase-4.7-detailed.md`.

`backend/models/decision_query_log.py`: add `QUERY_TYPE_SCAM_CHECK = "scam_check"` (fits `String(32)`, no migration). Only **scam_check** (user-initiated) logs to `decision_query_log`. **Drift is proactive** and stamps the empathy `empathy_fired` event stream (via #1.2) — it must NOT be written to `decision_query_log`, because `/charts/decision-adoption` (`backend/api/admin/analytics.py`) aggregates every row with no `query_type` filter and would inflate the G1/G2 adoption / active-user metrics. Two separate streams: `decision_query_log` = user-initiated decision queries; empathy events = proactive nudges.

### DoD
- `QUERY_TYPE_SCAM_CHECK` added to `VALID_QUERY_TYPES`; no migration needed (documented check).
- Test asserting drift does NOT appear in `decision_query_log`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01Suj5ENcPR7DooNU7GowadB
