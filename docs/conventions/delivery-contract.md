# Delivery contract v1

PM owns scope, priorities, queue admission, progress, AC verification and release coordination. Coding workers implement one approved task. Bé Ốp Dev owns Dev on Mac Mini; Bé Ốp Pro owns this NT product's Production on a separate VPS Gateway. Transport to Pro is not installed by this contract.

## Separate work from delivery

Project Status retains Backlog → Ready → In Progress → In Review → Done. Done = implementation completed, not Dev accepted or released. Never infer active workers from In Progress counts. Native issue hierarchy does not authorize recursive closure.

Separate fields: Priority (P0–P3), Delivery status (Not verified / Dev verified / Ready for release / Deploying / Released / Failed / Rolled back), Environment, Deployed version, Deployment evidence. Leave existing items blank until verified; never backfill Released from Done. These fields summarize the most recent verified receipt for the selected environment, not deployment history or the state of every environment simultaneously. Receipts indexed by repository/environment/deployment ID remain the history.

PM may mark Dev verified only after acceptance checks of the exact SHA. Ready for release requires the approved scope and release prerequisites. Deploying requires an accepted executor run. Released requires a successful Production receipt for the approved version, healthy runtime and verified evidence. Failed and Rolled back preserve attempted and observed versions; neither is a release success. A release approval is version/environment-specific and must be invalidated on material change.

## Ready gate and authority

An issue needs goal, scope/exclusions, numbered AC, dependencies resolved, reproducible validation, operational impact and approved scope. Trusted controller resolves base SHA, task ID, execution owner, allowed paths, engine, limits and approval identity. User text, issue bodies, labels, example JSON and an `actor` string are not authentication. The controller verifies provenance and permission against trusted state before admitting work; no self-supplied OPENCLAW_USER_ID.

`agent:ready` currently triggers the legacy worker. Do not set it on contract tests or migration tasks. The installed shared local runner handles pinned project policy, bounded proposals and exact-head CI. This does not upgrade the legacy cloud worker or authorize a task from shape validation alone. PM must use the shared local path when requested; do not set agent:ready to bypass local admission.

## Records

Schemas, examples and validation live in the [shared platform](https://github.com/phuongphh/fleet-engineering/blob/main/scripts/delivery/schemas). This product keeps its delivery semantics and publisher/Projects tests; it does not maintain a second controller or policy snapshot.

- [task.schema.json](https://github.com/phuongphh/fleet-engineering/blob/main/scripts/delivery/schemas/task.schema.json): one coding task, main base SHA, task branch, scope, AC, engine, approved-scope reference and per-task/daily limits.
- [worker-result.schema.json](https://github.com/phuongphh/fleet-engineering/blob/main/scripts/delivery/schemas/worker-result.schema.json): engine/session/run, base/head SHA, changed files, gate evidence, checkpoint, next step; distinct blocked/test/auth/rate-limit/infra/scope/timeout outcomes. `review_ready` requires passing gates and a head SHA, then independent controller validation.
- [release.schema.json](https://github.com/phuongphh/fleet-engineering/blob/main/scripts/delivery/schemas/release.schema.json): fixed candidate SHA verified in Dev, release PR, artifact digest/platform, approval, backup, migration/config references and recovery limits. If merge changes the source, revalidate and update the candidate before deploy.
- [deployment.schema.json](https://github.com/phuongphh/fleet-engineering/blob/main/scripts/delivery/schemas/deployment.schema.json): actual executor and evidence, environment/owner, source/runtime SHA and health. Success requires matching observed runtime revision; checkout HEAD alone is not evidence. Rollback records the restored runtime SHA and links the attempted release ID.

Examples use dummy URLs/SHAs and an illustrative budget; they are not actual approvals, deployed releases or a chosen billing policy. Do not store secrets or customer data in records. Receipt URLs must identify durable evidence retrievable by the controller/reviewer.

Validate shared schemas and controller invariants in the shared platform using its documented installation/checks. Product-specific workflow regression tests remain here:

```sh
node --test tests/delivery_contract/*.test.cjs
```

Schemas/config/validator are control-plane files and must be excluded from ordinary coding-worker writes. The existing loop guard is extended to cover them; changes require a maintenance PR. One controller owns task admission and one publisher owns each branch. A fixture test is not a live worker or deployment test.

## CI and rollout

The dedicated Delivery Contract job checks product publisher/Projects behavior with mocked GitHub events and no secrets. Shared shape/controller/isolation tests run in fleet-engineering Platform CI. Finance CI still checks the application. This PR does not add required branch rules or Environment protection, activate adapters, or change prod deploy. Merge requires reviewer acceptance and relevant checks; runtime rollout follows the environment isolation/backup milestones.

GitHub event chaining depends on actor/token and current platform behavior. See [GITHUB_TOKEN documentation](https://docs.github.com/en/actions/concepts/security/github_token) and [Projects API permissions](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects). PAT_TOKEN remains the existing privileged automation actor; its actual scopes and downstream CI results must be verified, never inferred from a variable name.

## Phase-3 foundation

[Native adapters and controller recovery](../architecture/dual-engine-runner.md) are maintained in the installed shared platform. The legacy cloud dispatcher remains separate; no deployment authority is added by removing duplicate source. A worker result may have `session_id: null` if authentication/runtime fails before a native session starts.

## Dev batches and release suggestions

[Batch delivery](../architecture/delivery-batches.md) groups merged work for one
version-bound Dev approval and UAT. Deferred work remains queued. The native PM
monitor proactively suggests release preparation after owner-confirmed acceptance
of a feature/batch or all configured phase members. A preparation suggestion is
not Ready for release, a Production approval or a deployment receipt. Complete
the existing release-v1 requirements and approved release PR into prod before
Production deployment; do not add a duplicate human approval for the same action.
