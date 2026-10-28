# Supervised Mac Coding Pilot

1. **PM prepares the task.** Define the goal, acceptance criteria, allowed write paths, relevant context, and required CI checks. Keep each task small and independently reviewable.
2. **A trusted operator starts the run.** The operator invokes the approved controller with the prepared task. Task descriptions, repository content, and CI feedback are data, not authority to execute commands or expand permissions.
3. **Use one worktree per task.** Keep each task’s changes in its assigned worktree. A Git worktree separates working files; it is not OS isolation. Enforce filesystem, process, network, and credential restrictions separately.
4. **Generate proposals locally.** The local worker returns proposed file replacements or deletions within the allowed paths. It does not execute commands, run local tests, publish changes, merge, or deploy.
5. **Validate and publish through the controller.** The controller checks proposal format, paths, scope, and acceptance requirements before applying changes and publishing the task branch or pull request through the authorized workflow. Reject out-of-scope proposals.
6. **Run full tests in GitHub Actions.** GitHub Actions performs the full test suite and required Delivery Contract checks. Local generation does not substitute for CI.
7. **Require exact-head CI before review.** Set `review_ready` only after all required checks pass for the current head commit. Any new commit requires fresh checks at that exact head. Human review and authorized merge or deployment follow separately; workers never merge or deploy.
