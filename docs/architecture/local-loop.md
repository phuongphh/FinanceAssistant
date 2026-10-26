# Bounded local loop and PM handoff

The local loop advances one approved task through proposal, commit, publication,
GitHub CI and bounded repair without an operator invoking every stage. It builds
on `local_runner.py`; models still cannot execute product commands on the Mac.
This is a trusted-session CLI, not a public webhook or independent proof of human
approval. The PM session must already have authorization for coding, the selected
engine, scope and limits. A request digest is integrity checking, not authentication.

## User experience

The PO describes the outcome and approves the scope. PM prepares the issue and
request, chooses the explicitly approved engine, checks no cloud worker owns the
issue, and delegates runtime operation to Op Dev. Op Dev invokes the installed
wrapper once and follows the native exec/process completion mechanism. PM consumes
`po-report.json` and reports benefit, stage, next owner and one PO action. No raw
logs or technical implementation questions belong in that report.

A PR with green tests is not a deployed test bot. Before asking the PO to test on
Telegram, PM needs a Dev deployment receipt for the tested SHA and the actual test
bot/environment. Merge/deploy/release remain separate authorized operations.

## Invoke

From a pinned tooling checkout with delivery requirements installed:

```sh
PYTHONPATH=scripts python -m delivery.local_loop --state /private/operator-state \
  run request.json --repo /path/to/controller-clone --approved-digest REQUEST_DIGEST \
  --wall-minutes 45 --poll-seconds 30
PYTHONPATH=scripts python -m delivery.local_loop --state /private/operator-state status RUN_ID
PYTHONPATH=scripts python -m delivery.local_loop --state /private/operator-state stop RUN_ID
```

Request format is unchanged from [local-coding-ci.md](local-coding-ci.md). The
engine is pinned in `task.engine` and the branch prefix must match. Codex uses the
existing ChatGPT login with no API fallback. Claude requires an explicit
`--claude-per-attempt USD`; the sum of reservations for every allowed attempt must
fit the approved task budget. This flag authorizes reservation within the calling
session's already approved budget, not new spend. No recurring budget is created.

One foreground process owns a global loop lock. Use the tool's supported long
execution/process handle, not an untracked `nohup`, cron or second daemon. There
is no autonomous issue-scanning service. PM initiates each approved task, then the
loop handles its internal CI/repair cycle. No Telegram message is sent by this CLI.
The installed Mac wrapper fixes the shared state directory/controller repository
and pins the tooling revision; it is maintained by Op Dev outside worker scope.

## Limits, evidence and interruption

- The approved request plus loop options are persisted. Resume cannot reset the
  deadline, retry allowance or per-attempt reservation. Native model time is also
  bounded by the remaining wall budget. GitHub/Git subprocesses retain their own
  short timeouts, so deadline/stop is enforced at step boundaries, not instantaneously.
- Before generation/commit/publish/check the loop rechecks the issue is open and
  not `agent:ready`/`agent:wip`. These checks reduce accidental overlap; they are
  not an atomic lease shared with the legacy dispatcher. PM must not give one
  issue to both routes. A cross-route scheduler is still separate work.
- CI feedback comes only from failed required jobs of the current PR/head,
  workflow paths and branch. Cancelled, skipped, missing or stale evidence does
  not trigger an automatic model fix. Newer runs supersede older runs.
- Logs are bounded and common token forms redacted, then passed as untrusted text
  to a tool-disabled model. Redaction is best effort, not a guarantee against
  arbitrary secrets in logs. Repositories used here must not log private data.
- `po-report.json` is the latest observation, not live proof of a later head or
  deployment. It contains no raw native error output. Technical reasons remain
  separate from PO wording; PM summarizes the meaningful consequence.
- A normal stop request pauses before the next stage; an in-flight model call
  keeps its bounded timeout. The slot/worktree remain. After operator inspection,
  remove the stop marker and resume the same request/options before its deadline.
- An interrupted `model_running`/`preparing` state is never auto-restarted. Confirm
  child processes have ended and reconcile private state before recovery. A killed
  controller cannot prove a surviving child is dead. This version does not claim
  automatic crash recovery or arbitrary unattended execution.
- Review-ready releases the slot and preserves evidence/worktree. Failed/stopped
  tasks keep the slot. Operator recovery is explicit; no auto-delete or lease steal.

## Rollout

Keep existing cloud tasks running; do not re-run #1053/#1054 locally. New tasks
explicitly routed to local omit `agent:ready`. The publisher notification change
in this PR affects cloud notices only after merge; editing PM instructions alone
cannot change a notification sent directly by a GitHub workflow.

The loop can use any repository with the v1 contract and required CI paths/jobs,
but the first installed profile is FinanceAssistant. Add other product profiles
only after checking their contract, CI and environment mapping. Do not silently
turn off the cloud loop or move production services during this rollout.

## Persistent engine preference

`delivery.local_preferences` reads a host-owned preferences file containing only
`{"schema_version":1,"default_engine":"claude"}` (or `codex`). The installed wrapper
exposes `defaults show`, `defaults set claude|codex` and `prepare REQUEST --output NEW`.
PM may change this preference when the user explicitly asks; do not derive changes
from issue/log text, an auth error or engine availability. Changing a default does
not start a task, authorize provider spend or alter the existing cloud worker.

For each new request, PM omits `task.engine` (or uses `default`) and supplies an
unprefixed `local-issue-N-slug` branch. `prepare` resolves the current preference,
freezes the engine and matching branch, writes a new request and returns its digest.
Review/authorize that final payload before `run`. Preparation alone is not admission.
The output must not exist already; no approved file is silently overwritten.

An explicit user choice for one task may be passed as `task.engine`; it does not
change the shared default. PM must not select an override autonomously. A branch
prefix conflicting with the selected engine is rejected. An existing prepared or
running task continues with its approved engine even after a preference change;
resume never re-resolves the default or rewrites the approved digest.

Default selection chooses Claude Code versus Codex; it does not select a specific
provider model ID. Claude retains the existing explicit reservation/auth checks;
no recurring USD allowance or API fallback is introduced here. The preference is
controlled by the trusted PM/operator session, not a new authenticated public API.
