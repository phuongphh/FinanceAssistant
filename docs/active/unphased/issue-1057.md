# Issue #1057

[Fleet pilot] Explain the local loop's PO handoff in a short guide

## Outcome
Create docs/examples/local-loop-po-pilot.md with a concise Vietnamese guide (under 250 words) for the Product Owner: the local worker creates a PR and verifies CI; PM handles technical questions; do not ask the PO to test Telegram until a Dev deployment for that version is verified. Explain what the PO should do at each stage. This document-only task validates the one-command local supervisor.

## Scope and acceptance
Only docs/examples/local-loop-po-pilot.md changes. No code, workflow, dependency, credentials or deployment changes. Use Codex with existing ChatGPT login; at most 10 minutes model time and one CI repair, 20 minutes wall time. GitHub CI + Delivery Contract must pass for the PR head. Stop at review-ready, no merge/deploy. Authorized as a bounded pilot of the user's local-loop implementation request; do not label agent:ready.
