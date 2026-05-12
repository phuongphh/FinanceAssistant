# Issue #498

[Story] P4.1-A3: Cost guardrail middleware

**Parent Epic:** #493 (EPIC 1: Pre-Launch Hardening)

Wrap LLM calls qua cost-tracking adapter. Enforce per-user budget cap. Warning 80%, block 100%.

- [ ] Moi LLM call di qua cost_tracking_adapter (DeepSeek/Claude/Whisper)
- [ ] BudgetService: <80% -> pass, 80% -> warning 1 lan/thang, 100% -> BudgetExceededError
- [ ] Default cap: free=30,000 VND/thang, pro=100,000 (v1 all free)
- [ ] Operator /budget_set <user_id> <amount>
- [ ] Log vao llm_cost_log sau moi call
- [ ] Integration tests

Close #493
