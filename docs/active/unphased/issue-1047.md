# Issue #1047

[Fleet] Verify GitHub approval evidence before runner admission

Continue the approved fleet refactor after merged #1046.

Goal: replace self-declared task approval with a read-only GitHub evidence verifier and reviewable PM intake workflow, without activating product workers.

Scope: bounded task parsing, approval digest bound to task content, canonical issue-comment references, allowlisted immutable GitHub account/repository IDs, current permission/issue/dependency/base checks, durable evidence with ledger grants, and pre-attempt revalidation through the coordinator. Add offline adversarial tests and a preparation/verification CLI. Default policy remains disabled with no approved live spending budget.

Acceptance criteria:
1. Changing scope/AC/base/engine/budget or approval batch invalidates the approval digest; task-supplied actor strings do not grant authority.
2. Wrong author/repository/issue, edited/stale approval, closed issue, incomplete dependency, API failure and disabled policy all fail closed.
3. Verified evidence and grant are persisted atomically; repeated admission does not start another worker; recheck approval before each retry.
4. PM can prepare the exact review payload without secrets, posting messages or starting a worker.
5. Document separate PM/controller/worker identities, cloud host and Codex auth prerequisites. Shared owner credentials are explicitly not proof of human approval.

Exclusions: no Telegram messages, provider spend, copied auth cache, cloud resource purchase, Production changes or legacy dispatcher cutover. No agent:ready label; this is already-authorized control-plane maintenance. Cloud host selection remains an independent rollout dependency.
