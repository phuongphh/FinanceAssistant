# Issue #468

[Story] P4.1-A3: Cost guardrail middleware

**Parent Epic:** #463 (Epic A: Pre-Launch Hardening)

## Description
Moi LLM call (DeepSeek/Claude/Whisper) di qua cost_tracking_adapter de enforce per-user monthly budget cap.

## Acceptance Criteria
- [ ] Migration 4.1.01: tables user_cost_budgets + llm_cost_log
- [ ] cost_tracking_adapter wrap all LLM adapters
- [ ] BudgetService.check_and_reserve(): <80% -> pass, >80% -> 1-time warning, >=100% -> BudgetExceededError
- [ ] Log moi call vao llm_cost_log
- [ ] Default cap: free=30,000 VND, pro=150,000, cfo=400,000 (all = free hien tai)
- [ ] Operator command /budget_set <user_id> <amount>
- [ ] Integration tests

## Estimate: ~2 days
## Dependencies: None

Close #463
