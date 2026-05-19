# Strategy

If not met: do not move to MVP.

1. Keep target segment focus.
2. Keep trust guardrails explicit.
3. Observe weekly operating metrics:
   - System: extraction success rate, P95 latency, cost per active user.
4. **Add internal trust risk explicitly**:
   - Founder access is also logged and visible to owners.
5. **Add UI navigation + date consistency baseline**:
   - In flow `Twin -> Lộ trình`, CTA `Quay về Twin` must always route to `Twin menu root`, never remain in `Lộ trình` stack.
   - Any missing route or invalid state must fallback to `Twin menu root` and log telemetry (`fallback_reason`, `source_menu`, `target_menu`).
   - All user-facing date rendering uses locale-driven format policy: `vi-VN => dd/MM/yyyy` as default baseline.

## 6-week execution plan

- Any decision deviating from docs must be updated within 24h.
- Permission and pipeline changes require cross-review.
- Instrument from day one: token, job status, deny/allow audits.
- UI/UX consistency is mandatory: menu fallback, date format, and language behavior must be deterministic across all screens.
