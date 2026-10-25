# Dual-engine runner foundation (phase 3)

Continues issue #1045 after delivery-contract PR #1044. The library provides native
CLI adapters, a persistent admission/lease ledger and a reference coordinator.
**It is not connected to the live dispatcher or PM/Telegram.** The existing
agent-worker.yml remains the legacy worker until isolated executors and trusted
admission are integrated and validated separately. No deploy/publish is performed
by this library.

## Responsibilities and interfaces

- `scripts/delivery/engines.py`: runs a pinned CLI as a separate process group,
  filters inherited credentials, parses native session/usage/error events, bounds
  output and runtime, and stops/reaps the process group on timeout or cancellation.
  `completed` means only that the engine finished; it never means review-ready.
- `controller.py`: SQLite WAL ledger outside the worker workspace. An authenticated
  controller/operator records a verified grant bound to the entire task digest.
  Model/issue text cannot approve itself. The public Python methods are trusted
  controller interfaces, not authorization endpoints; never expose `approve` or
  `reconcile_dead` directly to a worker or trust a supplied actor/reference string.
- `assessment.py`: classifies independently observed gates and changed paths.
  It blocks traversal, secrets and control files even when the task allows broad
  paths. It does not execute or interpret model claims as test evidence.
- `loop.py`: coordinates injected trusted executor/gate callbacks, writes atomic
  private result/checkpoint metadata, resumes a specific session for a fix, and
  retries only within admission limits. Execution is disabled by default; there
  is deliberately no automatic local product launcher.

Task validation is required before admission. The coordinator validates the task
and result schemas. `worker-result.session_id` now permits null for failures before
session creation; no fake session ID is generated. The controller uses explicit
native IDs, never `--last` or `--continue`.

## State, fencing and recovery

Controller state must be 0700 and its database 0600 under the controller's OS
identity, outside product workspaces. Run the actual worker under a different,
isolated identity/host; a private file owned by the same user is not an OS boundary.
The ledger serializes admission with SQLite `BEGIN IMMEDIATE` and limits global
concurrency to one, including different repositories.

Each dispatch has a stable event/request ID. Replay returns the latest settled
checkpoint, never a reusable execution token. A task already review-ready cannot
start again under another event. Each attempt has a random fencing token; stale,
revoked or expired ownership cannot heartbeat or publish a successful result.

An expired lease does **not** permit takeover. Verify the previous executor stopped
and record its death receipt through the trusted reconciliation interface first.
A timeout result can settle after expiry only once the executor has stopped; this
exception cannot publish a review-ready result. Revocation fences the executor and
requires reconciliation before another admission.

A checkpoint records task digest, engine/session, base SHA, patch digest and result
reference. Metadata alone does not restore code. After a restart, resume requires
a trusted `restore` callback that restores and verifies an immutable workspace
artifact for that digest. Missing/mismatched artifacts fail closed. Executor death
before checkpoint completion requires reconciliation; raw private CLI events may
assist diagnosis but are not automatically promoted into a valid checkpoint.
A controller killed by the OS cannot enforce its own timeout: the isolated runner
must have an independent job deadline and process cleanup before rollout.

## Budget and retry policy

Each attempt reserves a finite amount before dispatch. Task totals include all
attempts and both engines' accounting under the approved task; daily totals cover
all tasks in this ledger and default to Asia/Ho_Chi_Minh midnight. Concurrent ledgers
must use the same approved daily policy and state store. A different database would
be a different budget domain and must not be used to bypass the fleet total.

Unknown actual cost never causes a refund. The full reservation remains charged
for admission accounting. Claude receives `--max-budget-usd`; Codex in this adapter
requires an existing ChatGPT login and never inherits OPENAI_API_KEY. Codex token
usage is recorded without inventing a dollar conversion. This is conservative
admission accounting, not a universal provider billing hard cap. Provider-side
limits are also required for paid unattended production use.

Attempts are capped at the task's max_fix_rounds + 1 (at most three); total active
execution time is shared across attempts. Independent gate failures can trigger a
fix using the same session. Repeated failed gates with the same patch stop early,
even if evidence URLs differ. Infrastructure retries use bounded backoff. Auth,
rate limit, timeout and scope errors checkpoint and stop rather than switching
account, model provider or billing method. Never run two engines against the same
active task; an engine change needs a separately authorized handoff after shutdown.

## Native adapter compatibility

Verified local versions on 2026-10-25:

| Engine | CLI | Auth in this adapter | Execution |
|---|---|---|---|
| Claude | 2.1.87 | Explicit ANTHROPIC_API_KEY, bare mode | JSONL output, dontAsk, finite budget, explicit --resume |
| Codex | 0.164.0-alpha.11.1 | Existing ChatGPT login | codex exec JSONL, sandbox, approval_policy never, explicit resume |

A version mismatch blocks execution pending validation. These are observed local
versions, not a claim that equivalent Linux packages or cloud auth are installed.
The model can be chosen explicitly by the trusted caller; the adapter does not
silently switch engines/providers or rewrite the user's account configuration.

Claude smoke mode exposes no tools. Its product mode exposes file tools only;
independent tests belong in the isolated gate executor. Bare mode skips ambient
hooks/settings discovery and requires explicit API auth. Codex ignores user config
and uses read-only/workspace-write sandbox policies, never bypass flags. Native
sandbox/permission flags supplement, but do not replace, disposable worker isolation.
Never invoke product mode on the Mac Mini account that owns Production credentials.

Sources: [Codex exec/resume](https://learn.chatgpt.com/docs/developer-commands#codex-exec),
[Claude programmatic execution](https://code.claude.com/docs/en/headless),
[Claude CLI reference](https://code.claude.com/docs/en/cli-reference).
Installed CLI help was checked as well; unsupported newer documentation flags are
not assumed available.

## Verification and activation prerequisites

Tests run offline in the Delivery Contract check and the application's CI. Fixtures
cover concurrent claims, replay after completion, lease expiry while the old worker
is active, stale fencing, private state, bounded budget/time, failed gates followed
by a fix, no-progress retries, auth/quota errors, process-group timeout and cancellation,
scope violations, and explicit checkpoint identity/restore requirements.

Bounded real local smoke tests also generated a pure function with each engine,
resumed the exact session and changed its behavior. A restricted AST interpreter
checked the generated function; no model-generated Python was executed directly.
These checks establish native adapter/session compatibility, not a cloud worker,
a 120-minute endurance run, or a product task deployed to Dev.

Before enabling v2 dispatch:

1. Provide authenticated PM admission with trusted identity/approval evidence and
   a controller state host that workers cannot read/write.
2. Provision isolated cloud executors and gate callbacks, immutable workspace
   artifacts, independent process deadlines, and dedicated scoped credentials.
   Existing local ChatGPT login does not establish Codex auth on GitHub runners;
   do not copy it or switch to paid API without a separate authorization choice.
3. Wire one dispatcher/publisher path to v2 under an explicit rollout flag, verify
   native runtime/model availability and provider budgets, then run one task per
   engine end-to-end with receipts. Retire legacy admission only during cutover.
4. Verify recovery after controller/worker crashes, external cancellation,
   budget exhaustion and publish retries without duplicate PRs.

Only then should PM advertise unattended product coding as ready. Production
release transport and Mac Dev/Production isolation remain separate milestones.

The next intake layer is described in [verified task admission](runner-admission.md).
Its disabled policy, GitHub account checks and atomic evidence storage supplement
this foundation; they do not provision workers or activate the legacy dispatcher.
