# Issue #591

[Story] P4.2.5-3.3: User status change action

**Parent Epic:** #575 (Epic 3: User Management APIs)

PATCH /api/admin/users/{user_id}/status body {status, reason}.

- [ ] Status: active / suspended
- [ ] Suspended user khong tuong tac duoc voi bot
- [ ] Reason required, min 10 chars
- [ ] Audit log day du from/to/reason

Close #575
