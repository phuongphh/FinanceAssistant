# Issue #583

[Story] P4.2.5-1.4: Audit log infrastructure

**Parent Epic:** #573 (Epic 1: Backend Foundation & Auth)

Moi admin action logged to admin_audit_log.

- [ ] Migration: bang admin_audit_log (id, admin_user_id, action, target_type, target_id, payload JSONB, ip_address, user_agent, created_at)
- [ ] Service log_action() voi Request context
- [ ] GET /api/admin/audit?limit=50&offset=0 paginated, filter options
- [ ] Append-only

Close #573
