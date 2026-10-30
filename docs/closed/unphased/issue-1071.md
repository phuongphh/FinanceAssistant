# Issue #1071

docs: align local coding guide with the shared fleet runtime

The local coding guide still says the FinanceAssistant auto-PR workflow publishes local task branches and that a product-local delivery config is required. Both are obsolete after fleet-engineering#1 and FinanceAssistant#1070.

Scope: update only docs/architecture/local-coding-ci.md. Keep it a concise product handoff to the shared platform, not a copy of the controller implementation.

Acceptance criteria:
1. Explain the PO workflow through Bé PM, with Ốp Dev operating the local runner and PR/CI evidence before Dev acceptance.
2. Describe the shared fleet-engineering package and reviewed project profile as authoritative; replace the old product-local tooling/propose/publish command sequence with a link to the shared operations guide.
3. State Claude is the persisted default, Codex can be chosen for one task or made the default by an explicit owner request, and existing tasks keep their approved engine/profile.
4. Local PRs belong to the shared controller, not product auto-PR. Preserve one coding slot, scoped proposals with model execution disabled, CI outside the Mac, approval/budget requirements and no automatic merge/deploy.
5. Be accurate about current limits: one supervised task, no durable multi-task queue or authenticated Pro transport claimed. Do not include credentials, chat IDs or host-specific absolute paths.
6. No product code, workflow, policy, schema, runtime state or environment changes.

Validation: exact changed-file scope review, owner-readable guide review, and the existing required CI jobs on the exact PR head. This task is part of the owner-authorized platform migration; issue text itself is not execution authorization. Stop at a review-ready PR.
