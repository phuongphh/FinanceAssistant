# GitHub workflow and delivery contract

Applies to FinanceAssistant (NT): coding branch → PR main → Dev Mac Mini verification → approved release PR prod → Production VPS (Bé Ốp Pro). Full contract: [delivery-contract.md](delivery-contract.md).

## Issues and hierarchy

Use `.github/ISSUE_TEMPLATE/delivery-task.yml`. PM turns an approved idea into scope, exclusions, numbered AC, dependencies and a validation plan. Native sub-issues describe hierarchy only: completing an Epic does not prove its children complete. List `Closes #N` explicitly only for each completed implementation issue. References in prose, branch names or commit messages are not authorization to close issues.

`Status` on Project #4 retains Backlog / Ready / In Progress / In Review / Done. Done means implementation completed, including manual completion; it is not a release record. Closed-as-not-planned is not moved to Done. Project automation never recursively closes children, never closes issues itself, and never updates deployment fields. A delayed event rechecks whether the issue remains closed/completed.

## PR ownership

- `agent/issue-*`: only the trusted agent-loop publisher creates the PR. Do not add this prefix to auto-pr.yml. Worker code cannot push/main/prod/merge.
- `claude/**`, `codex/**`: auto-pr is the legacy interactive publisher, serializes by branch, reuses any existing PR and preserves its body. A new PR is draft, with reference-only links; a human/PM provides acceptance evidence and explicit closing links.
- `claude/merge-prod-release-*`: excluded; release PRs are deliberately opened with base prod.
- One task/branch has one PR; do not reuse a closed task branch. Handle duplicate events and a concurrent creator by finding the existing PR.
- Privileged project/PR automation checks out trusted main, not task-branch scripts.

Use PRs for substantive changes, including this maintenance change. No direct push to main/prod. Existing automated issue-doc sync is a separate trusted documentation writer; no new direct-write exception is added here. User reviews and merges release PRs through GitHub; a coding or maintenance PR is not release approval.

## Admission and automation

`agent:ready` is an execution trigger in the current loop. Never add it just to test a template or board. PM checks approved scope, AC, dependencies, trusted authorization, test capability and runtime availability before admission. Board Ready alone does not enable execution. Existing jobs remain legacy until the controller/worker adapters enforce the v1 task contract; creating a template does not install that controller.

Auto-pr uses the existing PAT_TOKEN to allow follow-on CI; do not replace it blindly with GITHUB_TOKEN. Confirm actual run/head/check state on a new PR. No token value belongs in a task, issue, receipt or repository.

A release/deployment failure does not reopen completed code by itself; record the delivery failure and create/link a fix task. Preserve per-environment immutable receipts; board fields are only a current summary.
