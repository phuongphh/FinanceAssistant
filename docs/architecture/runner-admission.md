# Verified task admission (phase 3b)

This adds a controller-side intake path to the runner foundation merged in #1046.
The live legacy dispatcher remains unchanged. `.github/fleet-admission.json` is
**disabled**, with zero product coding budgets. The earlier USD 1 smoke allowance
is not a recurring coding budget. There is no listener, workflow trigger, automatic
comment writer, worker provisioner or publisher in this change.

## PM preparation and operator evidence

1. PM prepares a task v1 file, including goal/AC, scope, dependencies, exact main
   ancestor SHA, engine, task limits, daily policy reference and approval scope ID.
   The branch must be `agent/issue-N-<simple-slug>` for that issue's publisher.
2. Run `PYTHONPATH=scripts python -m delivery.admission prepare task.json` from the
   trusted controller checkout. Supply `--policy`/`--config` only from controller
   configuration, never from the submitted task. This is offline and creates no
   grant. It prints the full review content and an exact approval line:
   `fleet-approve-v1 sha256:<digest>`.
3. The configured approver reviews the full payload and, if approved, posts that
   line as a new comment on the task issue. Editing a comment invalidates it.
   Populate `approval.reference`, `actor`, and `approved_at` from the resulting
   GitHub record. Those three generated metadata fields are excluded from the
   approval digest; `scope_id` and every other task field remain bound to it.
   Re-run preparation to confirm the digest is unchanged. Never ask an approver
   to approve an opaque digest without the payload.
4. The trusted controller verifies GitHub evidence using GET requests to the fixed
   `api.github.com` origin. It checks immutable repository/account IDs, current
   write/maintain/admin permission, open task issue, completed same-repo issue
   dependencies, base ancestry, exact comment body/identity and approval age.
   Unsupported dependency forms fail closed. Approval expires within the configured
   lifetime (at most 24 hours). Deleted, edited or unavailable evidence blocks intake.
5. `Admission.admit(task, ledger)` requires an enabled policy with explicit positive
   task/day budgets and matching ledger configuration. It binds the grant to the
   full task digest and atomically stores verification evidence. It starts no worker.
   `Admission.execute(...)` composes admission with the reference coordinator,
   rechecking before each attempt and after successful model/gate execution, before
   accepting a result. The executor must still be explicitly enabled and isolated.

`verify` is a diagnostic CLI action that reads evidence but never writes a grant.
It uses `FLEET_GITHUB_READ_TOKEN` only when explicitly supplied; public metadata can
be read without a token, while permission checks may require one. Do not pass secrets
on the command line. Errors do not echo API response bodies or submitted task text.
The API client refuses redirects and ambient proxies and bounds response size/time.
It cannot mutate GitHub or call arbitrary approval URLs.

## Identity boundaries and remaining integration

GitHub proves which **account** authored a comment, not that a human typed it.
If PM, Sen and a human all share the owner's writable GitHub credential, this is not
independent human approval. Before enabling this route, PM needs a distinct identity
that cannot act as an allowlisted approver. The controller needs read-only evidence
access, its own private state/OS identity, and an operator-owned policy checkout.
Workers must not access those credentials, policy, ledger, or approval methods.
The existing shared Mac account is not such an isolation boundary.

The database stores admission evidence with the grant in one transaction. Repeated
admission preserves the original evidence; a changed policy or evidence cannot reuse
that grant. Replaying a completed event does not launch a second executor. Existing
grants without evidence cannot be silently upgraded. Policy changes require explicit
migration/new admission; do not swap to another database to bypass task/day limits.
The underlying `Ledger.approve` remains an internal trusted API for compatibility;
never expose it directly in place of `Admission`.

Upstream approval is rechecked at attempt/result boundaries, not continuously during
a running model call. Immediate cancellation still uses the controller's revoke/lease
path. If revalidation fails after execution, the run remains fenced until a trusted
operator reconciles executor death; it cannot publish a review-ready result. A future
publisher must revalidate again at publish time. External cancellation, durable
workspace artifacts, an independent supervisor deadline, and actual worker deployment
remain necessary. No authentication token or model prompt belongs in public receipts.

## Local or cloud worker

The same intake works with a dedicated cloud executor or a Linux VM on the Mac Mini.
Placement does not change GitHub branches, PM responsibilities, or deployment ownership.
A checkout/worktree under the Mac's Production account is not worker isolation.
The controller/publisher and arbitrary product test execution must have separate
credentials and privileges, including inside a VM; merely creating a VM does not
separate a test process from the coding engine's credentials in that same VM.

For Codex subscription access, headless device login is documented, but account
availability and the installed Linux CLI version must be checked on the actual worker.
The advanced auth-cache CI workflow is restricted by the official guide to trusted
private automation and explicitly excludes public/open-source repositories. This
repository is public: do not copy personal `auth.json` into its Actions secrets/jobs.
Use the existing local ChatGPT login only for the already-approved local smoke checks;
select and validate the worker authentication path before unattended rollout. No API
billing fallback or credential transfer is performed by this PR.

Sources: [GitHub issue comments](https://docs.github.com/en/rest/issues/comments#get-an-issue-comment),
[GitHub collaborator permission](https://docs.github.com/en/rest/collaborators/collaborators#get-repository-permissions-for-a-user),
[Codex headless authentication](https://learn.chatgpt.com/docs/auth#login-on-headless-devices),
[Codex account auth in CI/CD](https://learn.chatgpt.com/docs/auth/ci-cd-auth).
