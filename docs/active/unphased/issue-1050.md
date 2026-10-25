# Issue #1050

[Fleet pilot] Document the supervised Mac coding and CI workflow

Small documentation task to verify the user-approved local coding workflow end-to-end.

Scope: create docs/examples/local-coding-pilot.md only. Explain in concise English: PM prepares a scoped task, a trusted operator invokes one local proposal worker, changes stay in a separate worktree, the controller validates and publishes a task branch, full tests run on GitHub Actions, and review-ready requires exact-head CI. State that worktrees are not OS isolation and that workers do not deploy or merge.

Acceptance: one short Markdown file, no application or workflow changes, actual PR CI passing on the published head. Local code generation uses Codex ChatGPT auth with execution tools disabled; no product code/test is executed on Mac. No agent:ready label and no Production release.

This is a supervised pilot under the current user's authorization; it does not activate an unattended queue.
