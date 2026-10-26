# Issue #1059

[Fleet] Persist Claude as the local runner default with PM-controlled switching

## Outcome
Use Claude Code as the default local coding engine for new tasks. A direct user instruction to PM can change the shared default to Codex (or back to Claude), with readback confirmation.

## Scope
Host preference file and thin CLI for show/set/prepare. Resolve the engine before approval/digest; keep prepared/running requests unchanged after default changes. Explicit one-task choices do not mutate the global default. Update installed wrapper and PM/DevOps instructions.

## Acceptance
- Shared default is Claude and survives process/session restart.
- PM updates it only on explicit user instruction, verifies saved value and reports briefly.
- New tasks inherit the preference; existing task engine/digest remains frozen.
- No model/API invocation, recurring budget, auth changes or provider fallback is implied by setting a default.
- Test persistent switching, conflicting branches, invalid settings and preparation.

Control-plane maintenance authorized in the current user conversation. Do not add agent:ready.
