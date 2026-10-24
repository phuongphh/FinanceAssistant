# Issue #483

[Story] P4.1-A3: Cost guardrail middleware

**Parent Epic:** #478 (Epic A: Pre-Launch Hardening)

Moi LLM call di qua cost_tracking_adapter de enforce per-user monthly budget cap.

- [ ] Migration: tables user_cost_budgets + llm_cost_log
- [ ] BudgetService: <80% cap -> pass, >80% -> warning, >=100% -> block
- [ ] Default cap: free=30,000 VND/thang
- [ ] Operator command /budget_set <user_id> <amount>
- [ ] Integration tests

Close #478
