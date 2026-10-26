# Proactive PM delivery notifications

A conversational promise to watch a PR does not schedule future work. The PM had
an empty heartbeat and no delivery-monitor job. This observer supplies that missing
execution mechanism through an OpenClaw **command** automation, without recurring
LLM calls or relying on the original Telegram conversation remaining active.

## Behavior

Every five minutes while the Mac/Gateway is running, a pinned Python command reads
GitHub metadata for configured repositories. It discovers new coding branches
`agent/issue-N-*`, `claude/local-issue-N-*` and `codex/local-issue-N-*` after a configured
cutoff, and retains tracked PRs to observe closure/merge. Explicit watch numbers
allow an existing PR to be notified once; old unrelated PRs are not backfilled.

Before asking the PO to merge, it verifies the current open, non-draft PR belongs
to the configured repository/base, is mergeable, has no active changes-requested
review, and the latest runs/jobs of each configured required workflow passed for
that PR/head/branch. Missing, pending, cancelled, skipped, foreign or stale checks
cannot produce a merge-ready notification. A newer run supersedes an older one.
The initial FinanceAssistant profile requires CI/pytest, Delivery Contract/contract
and Code Review/review. This is automated-check evidence, not a guarantee that
human product acceptance or Dev deployment occurred.

PO messages describe the stage and next action, with one PR link. They never ask
the PO to choose technical implementation details or test a PR on the running
Production bot. Merged means integrated; Dev and release evidence remain separate.
Failed checks/conflicts/requested changes are assigned back to PM/coding workflow
in the wording; this observer does not actually dispatch coding or post comments.
Configured issues with agent:blocked also produce an actionable notification.

## Delivery and durable state

Messages are sent through native `openclaw message send --channel telegram
--account pm` to a configured owner chat already verified against PM's allowlist.
No bot token is copied into this program, repository or scheduler command.
The scheduler itself uses no fallback delivery, preventing a second copy.

State is owner-only, locked and atomically saved. A phase/head fingerprint is
recorded only after a Telegram message ID is acknowledged. Stable state produces
no more messages; a changed head or meaningful state transition may notify again.
Failed sends remain pending for a later poll. There is an unavoidable delivery
ambiguity if Telegram accepts a message but the local process dies before saving
its acknowledgement: this is retryable delivery, not an exactly-once guarantee.
Two consecutive polling failures produce one short outage alert; repeat alerts
are limited to once per hour. If Telegram itself is unavailable, scheduler errors
and pending state remain the diagnostic evidence; delivery cannot be guaranteed.

`--dry-run` previews messages and never sends or writes a checkpoint. All GitHub
calls use GET. No merges, issue/label mutations, code execution, deployment or
automatic release/dependency activation is part of this monitor. In particular,
watching #1061 does not itself authorize activating #1062 when it finishes.

## Operation

```sh
PYTHONPATH=scripts python -m delivery.pm_monitor --config /path/pm-monitor.json \
  --state /private/pm-monitor-state --dry-run
```

Use the native cron API/CLI to register/update one command job with a stable
name/declaration key, agent pm, five-minute cadence and no fallback delivery.
Use argv rather than an interpolated shell string. Inspect native run history,
confirmed Telegram message IDs and persistent observer state after installation.
Do not add a duplicate Codex heartbeat or a second OpenClaw agent-turn watcher.

When PM promises future monitoring, it must verify a durable job actually covers
the repository/task and delivery destination. If no such mechanism exists, create
one within authorized scope or state that ongoing monitoring has not been enabled.
A manual status response, process accepted or empty heartbeat is not that proof.

The monitor keeps working after this Codex conversation closes, provided the Mac
and OpenClaw Gateway remain running. It cannot poll while the Mac sleeps/offline;
it catches up on the next run. Add repositories only after verifying their trusted
required workflow/job names and recipient. Monitor configuration and installed
source are maintained by Op Dev; PM owns scope, interpretation and PO communication.
