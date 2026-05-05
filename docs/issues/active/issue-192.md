# Issue #192

[Story] P3.7-S10: Audit logging + cost dashboard

**Parent Epic:** #182 (Epic 3: Polish, Audit & Testing)

## User Story
As a product owner monitoring Phase 3.7, tôi cần detailed audit logs của every agent invocation để debug issues, identify expensive patterns, và verify cost stays within budget.

## Acceptance Criteria
- [ ] **DB model `AgentAuditLog`** trong `app/agent/audit.py`:
  - id, user_id, query_text, query_timestamp
  - tier_used, routing_reason
  - tools_called (JSON array), tool_call_count
  - llm_model, input_tokens, output_tokens, cost_usd
  - success, response_preview, error
  - total_latency_ms
- [ ] **Migration** tạo bảng `agent_audit_logs`
- [ ] **Logging integrated trong:**
  - DBAgent (Tier 2): log every query
  - ReasoningAgent (Tier 3): log every query
  - Orchestrator: log routing decision
- [ ] **Async logging** — không block main path (background task / fire-and-forget)
- [ ] **Admin dashboard endpoint** `/miniapp/api/agent-metrics`:
  - Today: total queries, total cost, latency p95
  - Tier distribution (% Tier 1/2/3)
  - Top 10 most expensive queries today
  - Top 10 slowest queries
  - Top 10 unclear/failed queries
  - 7-day cost trend
- [ ] **Daily aggregation job** (cron 23:59):
  - Compute daily metrics
  - Alert nếu cost >$5

## Cost Calculation Reference
- DeepSeek: ~$0.14/1M input, $0.28/1M output
- Claude Sonnet: ~$3/1M input, $15/1M output

## Estimate: ~1 day
## Depends on: Epic 2 complete
## Reference: `docs/current/phase-3.7-detailed.md` § 3.1
