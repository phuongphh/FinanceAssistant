# Supervised local coding with remote CI

This profile is now operated through the shared fleet-engineering platform.
For full operating instructions see the authoritative shared guide:
**[OPERATIONS-VI.md](https://github.com/phuongphh/fleet-engineering/blob/main/docs/OPERATIONS-VI.md)**

The reviewed task profile for this repository is **`projects/FinanceAssistant.json`**
in the shared platform's profile registry. The profile supplies project policy
and named CI gates. Each approved task separately pins its selected context,
write paths, engine and limits; the shared package owns the contract schemas.

## Roles and admission

The **Product Owner (PO)** raises requests and authorizations through **Be PM**.
The **PM** coordinates with **DevOps/Be Op Dev** to operate the runner.
For example: "Run FinanceAssistant issue N through the local loop; stop at a PR."
The PO does not need to prepare JSON, compute digests or run CLI commands.
DevOps operates one supervised local task at a time using the shared controller;
no task may start without explicit budget authorization from the PO/PM chain.
Unattended or PM-autonomous launch is not enabled.

## Model and engine

**Claude is the default coding engine** for tasks under this profile.
Codex may be selected as an explicit per-task override; any override must be
recorded in the task request before the approved digest is computed.
An explicit owner request such as "Change the local runner default to Codex"
asks PM to update and read back the persisted preference. Choosing Codex for one
task does not change that default. Existing tasks keep their approved engine
and profile even when the default changes. Do not change shared settings here.

## What the shared controller does

The shared controller (from the fleet-engineering platform) manages the full
local run lifecycle and is the **sole PR publisher** for `claude/local-issue-*`
and `codex/local-issue-*` branches. This repository does not require a local delivery config
prerequisite, manual propose/commit/publish sequence, or product-local runner.
Operators follow the platform's single-command bounded-loop invocation as
described in OPERATIONS-VI.md, referencing the `FinanceAssistant.json` profile.

## Preserved safety boundaries

The following constraints apply regardless of engine or invocation path:

- **No local execution.** The model receives selected UTF-8 context and returns
  JSON file replacements only. It never receives permission to run project
  setup, tests, hooks, build or deployment commands on the host.
- **One global coding slot.** Only one active task may be held at a time;
  a new task cannot begin while the slot is occupied.
- **Budget and authorization required.** Each Claude attempt requires an
  explicitly authorized reservation; this is not a recurring daily budget.
  No new provider spend is authorized by examples in this document.
- **No automatic merge or deploy.** CI evidence (exact-head, named GitHub
  Actions gates, open PR) is required before review-ready status; the
  controller never merges or deploys.
- **Current limits.** The runner supervises one task, including bounded CI fixes.
  A durable queue advancing across multiple tasks and authenticated handoff to
  the VPS Production DevOps agent (Be Op Pro) have not been installed.
- **Context review.** Explicit context selection must be reviewed for
  secrets and customer data before being sent to a model provider.
- **Worktrees are not OS isolation.** This design narrows model tools and
  input rather than permitting arbitrary project execution. It must not be
  advertised as safe for unrestricted shell access or untrusted extensions.

## CI evidence requirements

CI evidence requires one open PR for the branch, exact head SHA, `pull_request`
event, expected workflow paths, and successful jobs `CI/pytest` and
`Delivery Contract/contract` and `Code Review/review`. All required jobs are taken
from the pinned profile. A newer failed run supersedes an older successful
one. `worker-result.json` describes the observed commit; later PR changes
invalidate that observation. This is not a release receipt.

## Storage and interruption

The profile installs no product dependencies locally. A killed controller
leaves the task slot occupied; confirm the child process group is dead and
inspect the private checkpoint before operator recovery. `close` releases only
a review-ready task and preserves all files. Broader cleanup is a later
operator operation.

[local-loop.md](local-loop.md) documents the earlier product-local supervisor.
Use the shared OPERATIONS-VI.md guide for current commands and installation;
do not start a new task with the historical product-local tooling.
