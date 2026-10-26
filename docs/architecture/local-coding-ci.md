# Supervised local coding with remote CI

This profile runs on the existing Mac without a VM or product dependency installs.
It implements a deliberately bounded workflow: an operator approves a complete
request; a model proposes text changes; controller code writes a scoped worktree;
the existing auto-PR workflow opens a draft; GitHub Actions runs full tests.

This is **supervised** operation. It does not enable autonomous PM admission,
modify the legacy agent queue, merge PRs, or deploy. The GitHub evidence admission
proposal in #1048 is separate. Existing chat authorization can authorize this
operator-driven maintenance/pilot; it is not represented as an independently
verified GitHub approval. The task's approval timestamp records intake, not proof
that a particular message was authored at that time.

## Why the local profile does not need a VM

The model runs from a sterile temporary Git directory, not the product worktree.
The controller sends at most 256 KiB of explicitly selected UTF-8 task/context text.
The model returns JSON file replacements/deletions; it never receives permission
to execute project setup, tests, hooks, build or deployment commands on the Mac.
Claude has no tools in bare mode. The pinned Codex CLI disables shell, apps, plugins,
browser, computer, multi-agent, hooks and image tools, disables web search and uses
read-only sandbox/ignored user config. Host skill discovery is disabled with the
pinned CLI's experimental switch; this produces a native warning. Compatibility
must be reverified before changing CLI versions. No user-global config is modified.

Worktrees are not OS isolation. This design narrows the model's tools and input
instead of allowing arbitrary project execution under the Production account.
It is not a sandbox for arbitrary plugins or untrusted extensions, and must not be
advertised as safe for unrestricted shell access. Explicit context selection still
needs review for secrets/data before it is sent to a model provider. Do not put
customer data in task context. Full product tests stay in GitHub Actions.

## Operator workflow

Use a dedicated controller clone whose origin is the canonical HTTPS repository;
never use the running product checkout. Controller tooling must be a separately
reviewed checkout outside model write scope. `.github/delivery.json` must exist in
the approved base commit, so rollout to other repositories requires their contract
configuration first. One shared private state directory covers all pilot repositories.

Prepare a JSON object with `task` (v1 contract), `context_paths` and `write_paths`.
Choose a small dependency-free task, 1-20 exact context/write paths and no more than
10 changed files per proposal. The branch is `<engine>/local-issue-N-<slug>`;
`agent/issue-*` remains owned by the legacy publisher. An issue already labeled
`agent:ready` or `agent:wip` is rejected to avoid dispatching it twice.

Example command sequence, using the trusted tooling checkout:

```sh
export PYTHONPATH=scripts
python -m delivery.local_runner --state /private/operator-state begin request.json \
  --repo /path/to/controller-clone --approved-digest <sha256-of-canonical-request>
python -m delivery.local_runner --state /private/operator-state propose <run-id>
python -m delivery.local_runner --state /private/operator-state commit <run-id>
python -m delivery.local_runner --state /private/operator-state publish <run-id>
python -m delivery.local_runner --state /private/operator-state check <run-id>
python -m delivery.local_runner --state /private/operator-state close <run-id>
```

Compute the request digest with `delivery.controller.digest` after reviewing the
entire request. The digest prevents accidental request changes; possession of it
is not authentication. These commands are for a trusted operator. Do not expose
them as a Telegram/web endpoint or give a model authority to approve itself.
PM may prepare requests and read status, but unattended PM launch still requires
the separate identity/admission integration. User authorization already granted
for a task need not be requested again just to compute its digest.

`propose` uses Codex's existing ChatGPT login without API fallback. Claude requires
an explicitly supplied `--claude-reservation <USD>` for each attempt and the existing
API credential; the total reserved amount cannot exceed the task limit. This is
not a recurring daily budget. No new provider spend is authorized by examples.
A failed/unknown-cost Claude attempt keeps its reservation. A supervisor must enforce
fleet-wide recurring budgets before any unattended mode. No auth cache is copied
into GitHub Actions. Native output and session metadata stay in private local state.

The global active-task marker remains held through `awaiting_ci`/`ci_failed`, even
when no model process is running. Each controller operation takes an OS file lock;
restart does not silently clear the active task. `status` reads progress. On CI
failure, a trusted operator supplies bounded CI feedback using `propose --feedback`
and the same run ID, then commits/publishes again. The native session is resumed;
at most max_fix_rounds + 1 attempts and a cumulative task execution-time limit apply.
This version does not auto-ingest logs or run a background retry service.

## Publish and CI evidence

The controller validates all proposal paths before writing: no traversal, symlinks,
hardlinks, secret paths, control files, special files or duplicate edits. It checks
content again before committing and refuses unrelated/dirty/stale worktree state.
Git hooks and ambient global Git configuration are disabled for local operations.
Publication uses the exact commit SHA and compare-and-swap remote ref, plus an
ancestry check on subsequent publishes. It cannot overwrite someone else's new head
or force a history rewrite. The controller clone's origin is rechecked before push.

The existing auto-pr workflow is the sole PR creator for these branches; local
runner neither opens a competing PR nor changes its body/state. CI evidence requires
one open PR for that branch, exact head SHA, pull_request event, expected workflow
paths and successful actual jobs `CI/pytest` and `Delivery Contract/contract`.
Missing, pending, skipped, failed, foreign-PR or stale-head checks cannot produce
review_ready. A newer failed run supersedes an older successful run. On success,
`worker-result.json` is validated against the shared contract. It describes the
observed commit; later PR changes invalidate that observation and must be checked
again. It is not a Dev verification or release receipt.

## Storage and interruption

There is no 60 GiB prerequisite. The bounded profile checks for 10 GiB free before
preparation/proposal; this is a conservative pilot stop threshold, not a provider
minimum. It installs no product dependencies locally. Per-attempt native output is
bounded by the existing engine adapter; selected context/proposal size is 256 KiB.
Operator-managed session caches and repository history still need periodic review.
Do not auto-delete old worktrees, dirty changes, native evidence or product data.

A killed controller leaves the task slot occupied, especially in `model_running`.
Confirm the child process group is dead and inspect the private checkpoint/worktree
before operator recovery. The CLI does not auto-steal/restart such a task. The
normal timeout stops the engine process group; a controller SIGKILL still needs
external process supervision for unattended operation. `close` releases only a
review-ready task and preserves all files. Broader recovery/cleanup is a later
operator operation, not a hidden reset.

Official native setting reference:
[Codex config](https://learn.chatgpt.com/docs/config-file/config-reference).


The [bounded local loop](local-loop.md) now provides a single invocation for this
sequence, including verified CI feedback and limited automatic fixes. It retains
the trusted-session authorization and no-local-execution boundaries described here.
