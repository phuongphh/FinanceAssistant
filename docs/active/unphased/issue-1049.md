# Issue #1049

[Fleet] Run supervised local coding proposals with GitHub CI gates

Implement the user-approved Mac Mini workflow without a new VM: one scoped task/worktree at a time, Claude/Codex propose file changes locally, full tests on GitHub Actions.

Scope: operator-authorized task digest, bounded context/outputs, native proposal-only engine profile, validation and controlled file writes, persistent one-task lock through CI, explicit commit/push to a dedicated codex/local-* or claude/local-* branch, reuse the existing auto-pr publisher, and verify required GitHub Actions checks on the exact PR head. PM can prepare/status; no automatic legacy queue cutover.

AC: no model shell/test/deploy on Mac; traversal/symlink/control-path edits rejected; dirty/stale worktree and changed remote heads block publication; pending/stale/failed/missing CI cannot be review_ready; retries remain one task and one PR; bounded real pilot has receipts.

No VM/SSD purchase, dependency installation into product checkouts, Production changes, GitHub approval comments, auto-merge or agent:ready labels. This is authorized control-plane maintenance following #1046; #1048 stays a separate unmerged intake proposal. This supervised route uses explicit operator authorization, not a claim of authenticated autonomous PM admission.
