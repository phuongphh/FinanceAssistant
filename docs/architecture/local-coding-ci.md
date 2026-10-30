# Supervised local coding with remote CI

This profile is now operated through the shared fleet-engineering platform.
For full operating instructions see the authoritative shared guide:
**[OPERATIONS-VI.md](https://github.com/phuongphh/fleet-engineering/blob/main/docs/OPERATIONS-VI.md)**

The reviewed task profile for this repository is **`projects/FinanceAssistant.json`**
in the shared platform's profile registry. That profile pins the request format,
write-path allowlist, context size limits and CI gate requirements for this project.

## Roles and admission

The **Product Owner (PO)** raises requests and authorizations through the **PM**.
The **PM** coordinates with **DevOps/Be Op Dev** for operator execution.
DevOps operates one supervised local task at a time using the shared controller;
no task may start without explicit budget authorization from the PO/PM chain.
Unattended or PM-autonomous launch is not enabled.

## Model and engine

**Claude is the default coding engine** for tasks under this profile.
Codex may be selected as an explicit per-task override; any override must be
recorded in the task request before the approved digest is computed.
Engine defaults and pinned CLI settings are owned by the shared platform;
do not change them in this repository.

## What the shared controller does

The shared controller (from the fleet-engineering platform) manages the full
local run lifecycle and is the **sole PR publisher** for `fleet-local-runner`
branches. This repository does not maintain a separate delivery config
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
- **No durable multi-task queue or Pro transport.** There is no background
  retry service, persistent queue or elevated transport tier.
- **Context review.** Explicit context selection must be reviewed for
  secrets and customer data before being sent to a model provider.
- **Worktrees are not OS isolation.** This design narrows model tools and
  input rather than permitting arbitrary project execution. It must not be
  advertised as safe for unrestricted shell access or untrusted extensions.

## CI evidence requirements

CI evidence requires one open PR for the branch, exact head SHA, `pull_request`
event, expected workflow paths, and successful jobs `CI/pytest` and
`Delivery Contract/contract`. A newer failed run supersedes an older successful
one. `worker-result.json` describes the observed commit; later PR changes
invalidate that observation. This is not a release receipt.

## Storage and interruption

The profile installs no product dependencies locally. A killed controller
leaves the task slot occupied; confirm the child process group is dead and
inspect the private checkpoint before operator recovery. `close` releases only
a review-ready task and preserves all files. Broader cleanup is a later
operator operation.

See [local-loop.md](local-loop.md) for the single bounded-loop invocation
and OPERATIONS-VI.md for the full shared platform reference.
