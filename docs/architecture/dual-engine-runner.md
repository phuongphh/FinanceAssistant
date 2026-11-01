# Native engine adapters — shared platform

Claude/Codex adapters, task admission, leases, limits and receipts are maintained in the shared platform. No product-local engine module remains.

- [Operations through Bé PM](https://github.com/phuongphh/fleet-engineering/blob/main/docs/OPERATIONS-VI.md)
- [Migration, cutover and recovery](https://github.com/phuongphh/fleet-engineering/blob/main/docs/MIGRATION.md)
- [FinanceAssistant profile](https://github.com/phuongphh/fleet-engineering/blob/main/projects/FinanceAssistant.json)

The installed release and private host bindings are the operational authority; a file on main alone does not prove rollout. Credentials and runtime state stay outside this repository. The owner talks to PM; local DevOps operates the installed wrapper. Product tests and delivery evidence stay project-specific.

For FinanceAssistant, see [Dev batches and release suggestions](delivery-batches.md). A green PR is not a deployed Dev version, UAT or Production approval. Models remain proposal-only on the Mac. A per-task Codex choice does not change the persisted Claude default. Durable multi-task wake/resume and authenticated VPS Pro handoff require their own verified implementation.

Historical implementations and invocation examples remain available in Git history. Do not restore a product-local controller to bypass a blocked shared task.
