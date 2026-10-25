# Issue #1045

[Fleet] Add dual-engine runner foundation with durable leases and normalized receipts

## Goal
Continue the approved fleet refactor after PR #1044: prepare Claude/Codex CLI adapters and persistent controller primitives for bounded, resumable coding runs.

## Scope
Native CLI adapters, normalized failure/session/usage metadata, private output handling, process timeouts, durable admission/lease/reservation ledger, independent result gates, fixtures and documentation. Keep current production and legacy worker activation unchanged.

## Exclusions
No Production deploy, Telegram transport, account/auth transfer, API billing fallback, or automatic queue admission. A controller database is not worker OS isolation. Cloud placement and authenticated PM admission remain rollout prerequisites.

## Acceptance criteria
1. Both adapters identify their session and produce normalized results; resume uses an explicit session ID.
2. A process deadline stops and reaps the process group; auth/rate-limit/timeout are distinct outcomes.
3. Duplicate admission and expired-but-unreconciled leases cannot start a second worker; stale fencing tokens cannot publish.
4. Task and daily reservation budgets persist across retries; unknown cost never causes an unsafe refund.
5. Model completion is insufficient for review readiness; independent gates and allowed-path checks are required.
6. Offline failure cases and bounded real CLI smoke tests have receipts. Smoke authorization: current Codex conversation; Claude API total cap USD 1, Codex existing ChatGPT login only.

## Validation
Unit/fixture tests without product services, then read-only/no-tool code-generation smoke tests in temporary directories. GitHub CI validates the maintenance PR.

## Delivery
Control-plane maintenance PR into main. Dev Mac / Production VPS pipeline is unchanged. No agent:ready label: this issue tracks the maintenance work already in progress and must not dispatch the legacy worker.
