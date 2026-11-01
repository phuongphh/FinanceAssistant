# Issue #214

[Story] P3.8-S6: Add GetIncome tool to Phase 3.7 agent

**Parent Epic:** #205 (Epic 2: Multi-Income Streams)

## User Story
As the Phase 3.7 agent, I need a `get_income` tool để trả lời queries về thu nhập với filter và aggregation.

## Acceptance Criteria
- [ ] File `app/agent/tools/get_income.py`
- [ ] Tool description với **5+ examples** (critical cho LLM accuracy):
  - "thu nhập của tôi" → all streams
  - "thu nhập thụ động" → filter is_passive=True
  - "thu nhập chủ động" → filter is_passive=False
  - "thu nhập từ thuê BĐS" → filter type=rental
  - "lương tháng này" → filter type=salary
- [ ] Pydantic input: `stream_type` filter, `is_passive` filter
- [ ] Output: list of streams + aggregated stats
- [ ] Registered trong ToolRegistry
- [ ] **Critical test:** "thu nhập thụ động" → chỉ trả về rental + dividend + interest

## Estimate: ~0.5 day
## Depends on: P3.8-S4
