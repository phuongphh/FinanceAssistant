# Issue #1055

[Fleet] Automate bounded local Claude/Codex loop and report clearly to the PO

## Outcome
Let an authorized PM/operator session start one bounded local coding task and receive a concise PO-facing outcome without manually invoking every runner stage. Keep full product tests in GitHub Actions.

## Scope
Authorized controller maintenance: add a resumable loop over #1052, exact-head CI feedback and bounded automatic fixes, explicit engine/budget selection, stop/status and no duplicate cloud ownership. Install a pinned local runtime and document PM/DevOps handoff. Replace verbose publisher notifications with a short stage/next-action report; keep technical details in the PR.

## Acceptance
- Claude and Codex selected explicitly; no silent paid fallback.
- One task slot, bounded attempts/model time/wall time; restart does not reset limits; interrupted engine remains fenced.
- CI failure feedback must belong to this PR/head and must not execute locally.
- Reports state that CI/PR is not deployment and identify the PO's next action.
- Test supervisor success/fix/timeout/crash/duplicate/ownership cases; run a small real Codex pilot.

No merge, product deployment, legacy-workflow shutdown, public ingress or recurring Claude budget is authorized by this issue. Do not label agent:ready: this is the separately authorized maintenance work.
