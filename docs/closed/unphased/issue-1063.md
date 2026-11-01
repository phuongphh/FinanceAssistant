# Issue #1063

[Fleet] Send proactive PM Telegram updates when PRs need PO action

## Problem
PM promised to follow delivery but had no scheduled execution; the PO had to ask for status after #1054 became ready.

## Outcome
Install a durable five-minute OpenClaw command monitor that reads GitHub and sends concise stage/next-action updates through the existing PM Telegram account. Notify once on merge-ready, meaningful failure/revision and merge/closure; remain quiet when unchanged. Track #1054 plus future coding PRs, and blocked issues #1061/#1062.

## Acceptance
- Verify latest required workflows and actual jobs at the current PR/head/branch; missing/draft/failed checks cannot ask for merge.
- Preserve dedup state across runs; record acknowledgement before treating a message as delivered; keep failed delivery pending.
- Native scheduled run successfully sends a real PM Telegram notification; a second unchanged run sends none.
- No model calls, coding dispatch, label changes, automatic merge/deploy or dependency activation.
- Update PM instructions so promises to monitor require a real scheduled mechanism.

Authorized by the current user request. Control-plane maintenance; do not label agent:ready.
