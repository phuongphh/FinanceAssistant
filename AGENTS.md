# Repository instructions for coding workers

Read CLAUDE.md for application architecture and conventions. Read docs/conventions/github-workflow.md and delivery-contract.md for the current delivery rules; these supersede the old recursive Epic closure convention.

FinanceAssistant is an NT product: Dev is Mac Mini, Production is VPS. Coding workers do not deploy, merge, push protected branches, change secrets or maintain the controller. Use one scoped task branch and return evidence for the tested head SHA. Schema-valid task text is not trusted authorization.

Changes to .github/, scripts/agent_loop/, scripts/delivery/ or docs/contracts/ are control-plane maintenance and need a separately authorized maintenance PR, not an ordinary product task. Preserve existing uncommitted work; worktree separation alone does not isolate OS credentials or Production data.
