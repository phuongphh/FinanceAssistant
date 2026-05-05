# Issue #186

[Story] P3.7-S4: Build DB-Agent with DeepSeek function calling

**Parent Epic:** #180 (Epic 1: Tool Foundation & DB-Agent)

## User Story
As Bé Tiền nhận "Top 3 mã lãi nhiều nhất", tôi cần DB-Agent dùng DeepSeek function calling để translate Vietnamese query → `get_assets(filter, sort, limit)` call tự động.

## Acceptance Criteria
- [ ] File `app/agent/tier2/db_agent.py` với `DBAgent` class
- [ ] DeepSeek API via OpenAI SDK
- [ ] System prompt:
  - Vietnamese instructions
  - Tool selection rules
  - **5+ concrete examples** (query → tool call mapping)
  - Output format specification
- [ ] `answer(query, user)` method:
  - Send query + tools schema tới DeepSeek
  - `tool_choice="auto"`, `temperature=0.0`, `max_tokens=500`
  - Parse tool call từ response
  - Validate args via Pydantic input_schema
  - Execute tool via registry
  - Returns dict: success, tool_called, tool_args, result, error, fallback_text
- [ ] **Test queries PHẢI PASS:**
  - "Mã nào đang lãi?" → get_assets với gain_pct > 0
  - "Top 3 mã lãi nhiều nhất" → get_assets sort gain_pct_desc, limit 3
  - "Tài sản trên 1 tỷ" → get_assets với value > 1000000000
  - "Chi ăn uống tuần này" → get_transactions với category=food, date=this_week
  - "Tổng lãi portfolio" → compute_metric portfolio_total_gain
  - "Tháng này vs tháng trước" → compare_periods
- [ ] Cost per call < $0.0005
- [ ] Latency < 2 seconds (DB-Agent only)
- [ ] Error handling: no tool called, invalid args, API timeout, unknown tool
- [ ] Cache LLM responses by query hash (Redis, 5 min)
- [ ] Log full LLM response để debug

## Implementation Notes
- Tier 2 = single-step: take FIRST tool call only
- Cache key include user_id (tránh cross-user cache hit)

## Estimate: ~1.5 day
## Depends on: P3.7-S2, P3.7-S3
## Reference: `docs/current/phase-3.7-detailed.md` § 1.3
